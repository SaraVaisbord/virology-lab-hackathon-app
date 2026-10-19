"""Preprocessing tests on synthetic pages (no real documents)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from preprocessing import DEFAULT_SETTINGS, estimate_skew, preprocess, rotate

# BGR colours measured on the sample scans (see preprocessing.PreprocessSettings).
BLACK = (20, 20, 20)
TEAL_PEN = (120, 90, 10)  # blue-green ballpoint
YELLOW_MARKER = (90, 245, 245)


def _page(width=1200, height=900) -> np.ndarray:
    return np.full((height, width, 3), 255, np.uint8)


def _write(page, text, origin, color, thickness=3, scale=1.4):
    cv2.putText(page, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _ink_in(mask: np.ndarray, box) -> float:
    x0, y0, x1, y1 = box
    return float((mask[y0:y1, x0:x1] > 0).mean())


@pytest.fixture(autouse=True)
def _no_osd(monkeypatch):
    # Orientation detection needs Tesseract; these tests are about the image operations only.
    import preprocessing

    monkeypatch.setattr(preprocessing, "fix_orientation", lambda image, settings: (image, 0))


def test_form_lines_are_removed_but_text_is_kept():
    page = _page()
    _write(page, "12602233", (100, 200), BLACK)
    cv2.line(page, (60, 215), (1100, 215), BLACK, 3)  # the underline the value is written on
    views = preprocess(page, source_dpi=300)

    text_ink = 255 - views.print_binary
    assert _ink_in(text_ink, (100, 160, 330, 205)) > 0.08  # digits survive
    assert _ink_in(text_ink, (600, 205, 1100, 225)) < 0.01  # the line right of the text is gone
    assert _ink_in(views.lines, (600, 205, 1100, 225)) > 0.05  # ...and reported as a line


def test_pen_ink_goes_to_handwriting_layer_not_print():
    page = _page()
    _write(page, "PRINTED", (100, 200), BLACK)
    _write(page, "27-08-2026", (100, 500), TEAL_PEN, thickness=8)
    views = preprocess(page, source_dpi=300)

    pen_box = (100, 450, 450, 510)
    assert _ink_in(views.handwriting, pen_box) > 0.05
    assert _ink_in(255 - views.print_binary, pen_box) < 0.01
    assert _ink_in(views.handwriting, (100, 160, 330, 205)) < 0.01


def test_highlighter_is_removed_and_black_text_on_it_is_kept():
    page = _page()
    cv2.rectangle(page, (80, 150), (420, 220), YELLOW_MARKER, -1)
    _write(page, "2646", (120, 205), BLACK)
    views = preprocess(page, source_dpi=300)

    assert views.stats["highlighter_px_pct"] > 1
    marker_only = (350, 155, 415, 215)  # marker without text
    assert views.normalized[155:215, 350:415].min() > 240
    assert _ink_in(255 - views.print_binary, marker_only) < 0.01
    assert _ink_in(255 - views.print_binary, (120, 160, 230, 210)) > 0.08  # the digits on the marker remain print


def test_skew_is_estimated_from_form_lines():
    page = _page()
    for y in (150, 300, 450, 600, 750):
        cv2.line(page, (60, y), (1140, y), BLACK, 3)
    skewed = rotate(page, 2.0, (255, 255, 255))
    gray = cv2.cvtColor(skewed, cv2.COLOR_BGR2GRAY)
    ink = np.where(gray < 128, 255, 0).astype(np.uint8)
    assert abs(abs(estimate_skew(ink, DEFAULT_SETTINGS)) - 2.0) < 0.3


def test_rescale_to_target_dpi():
    views = preprocess(_page(600, 450), source_dpi=150)
    assert views.normalized.shape[:2] == (900, 1200)


def test_barcode_views_are_grey_variants():
    views = preprocess(_page(), source_dpi=300)
    assert len(views.barcode_views) == 5
    assert all(view.ndim == 2 for view in views.barcode_views)
