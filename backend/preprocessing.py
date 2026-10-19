"""Image preprocessing for scanned forms — runs locally, before barcode scanning, OCR and the LLM.

Every consumer needs a different picture of the page, so one scan is turned into several *views*:

    normalized    deskewed, evenly lit colour page, yellow highlighter removed   → display, LLM crops
    print_binary  black printed ink only, form lines removed, white background   → OCR (labels, printed numbers)
    handwriting   blue pen ink only                                              → LLM / handwriting crops
    stamps        red / purple stamp ink                                         → kept out of OCR
    lines         the removed form lines                                         → layout / debugging
    barcode_views several grey variants (plain, sharpened, upscaled, binarized)  → zbar tries each

Colour separation works in CIE-LAB on *smoothed* chroma: scanners leave thin coloured fringes around
black letters (measured on the samples: up to half of all "ink" pixels look magenta at the pixel level),
so chroma is median-filtered first — 1-2 px fringes vanish, real pen strokes (6-10 px at 300 dpi) remain.
All tunable parameters live in PreprocessSettings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass(frozen=True)
class PreprocessSettings:
    # Scale every page to this resolution (Tesseract is trained for ~300 dpi).
    target_dpi: int = 300
    # Page orientation (90/180/270) via Tesseract OSD; ignore its answer below this confidence.
    # Run on a downscaled copy for speed. (Some sample pages are landscape screen printouts scanned sideways.)
    orientation_min_confidence: float = 1.5
    orientation_scale: float = 0.5
    # Deskew: only correct small scanner skew; larger angles are a rotation problem, not skew.
    max_skew_degrees: float = 8.0
    # Background estimation for even illumination (kernel ≈ 1/30 of the page width).
    background_kernel_ratio: float = 1 / 30
    # Sauvola binarization (window in px at target_dpi, k sensitivity).
    sauvola_window: int = 41
    sauvola_k: float = 0.18
    # Chroma smoothing kernel that removes scanner colour fringes (must be odd; > fringe width, < pen stroke).
    chroma_median_ksize: int = 7
    # Colour classification in the LAB a*b* plane (hue angle in degrees, chroma = colour strength).
    # Measured on the samples: black print chroma < 10; teal pen hue ≈ 186°, chroma ≈ 19;
    # yellow highlighter hue ≈ 110°, chroma ≈ 35 (bright on paper, olive L≈47 over stickers).
    colored_chroma_min: float = 12.0  # below this, ink counts as black/grey print
    pen_hue_range: tuple[float, float] = (140.0, 290.0)  # blue / teal / green pens
    highlighter_hue_range: tuple[float, float] = (60.0, 135.0)  # yellow / yellow-green marker
    highlighter_chroma_min: float = 18.0
    # Inside a highlighted area, pixels darker than this (L*, 0..100) are ink written on the marker — kept.
    highlighter_ink_l_max: float = 40.0
    # Form lines: a run of ink longer than this fraction of the page width/height is a ruling line.
    line_min_length_ratio: float = 0.035
    # Speckles smaller than this (px area) are noise.
    min_component_area: int = 12
    # Barcode views: extra upscale factor for small barcodes, and a downscaled view (zbar sometimes decodes
    # thick, noisy bars only at lower resolution — measured: 2 barcodes found only by the old 171-dpi input).
    barcode_upscale: float = 1.5
    barcode_downscale: float = 0.6


DEFAULT_SETTINGS = PreprocessSettings()


@dataclass
class PageViews:
    normalized: np.ndarray  # BGR
    print_binary: np.ndarray  # uint8, 0 = ink, 255 = paper
    handwriting: np.ndarray  # uint8 mask, 255 = blue ink
    stamps: np.ndarray  # uint8 mask, 255 = stamp ink
    lines: np.ndarray  # uint8 mask, 255 = removed form lines
    barcode_views: list[np.ndarray] = field(default_factory=list)  # grey images
    skew_degrees: float = 0.0
    stats: dict = field(default_factory=dict)


# ── building blocks ──────────────────────────────────────────────────────────


def rescale_to_dpi(image: np.ndarray, source_dpi: float, target_dpi: int) -> np.ndarray:
    if not source_dpi or abs(source_dpi - target_dpi) < 5:
        return image
    scale = target_dpi / source_dpi
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=interpolation)


def sauvola(gray: np.ndarray, window: int, k: float, dynamic_range: float = 128.0) -> np.ndarray:
    """Sauvola local threshold (robust to uneven lighting and faint ink). Returns 0 = ink, 255 = paper."""
    img = gray.astype(np.float64)
    mean = cv2.boxFilter(img, -1, (window, window), borderType=cv2.BORDER_REPLICATE)
    sq_mean = cv2.boxFilter(img * img, -1, (window, window), borderType=cv2.BORDER_REPLICATE)
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0))
    threshold = mean * (1 + k * (std / dynamic_range - 1))
    return np.where(img > threshold, 255, 0).astype(np.uint8)


def normalize_illumination(gray: np.ndarray, kernel_ratio: float) -> np.ndarray:
    """Divide by the estimated paper background: removes shadows, yellowed paper and scanner gradients."""
    size = max(15, int(gray.shape[1] * kernel_ratio) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (size, size)))
    return cv2.divide(gray, np.maximum(background, 1), scale=255)


def _line_masks(ink: np.ndarray, ratio: float) -> tuple[np.ndarray, np.ndarray]:
    """Horizontal / vertical ruling lines in an ink mask (255 = ink)."""
    h_len = max(25, int(ink.shape[1] * ratio))
    v_len = max(25, int(ink.shape[0] * ratio))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return horizontal, vertical


def estimate_skew(ink: np.ndarray, settings: PreprocessSettings) -> float:
    """Skew angle (degrees) from the form's long horizontal lines — forms have plenty of them."""
    horizontal, _ = _line_masks(ink, settings.line_min_length_ratio)
    segments = cv2.HoughLinesP(horizontal, 1, np.pi / 1800, threshold=100,
                               minLineLength=int(ink.shape[1] * 0.1), maxLineGap=10)
    if segments is None:
        return 0.0
    # OpenCV 4 returns (N, 1, 4), OpenCV 5 returns (N, 4).
    angles = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in segments.reshape(-1, 4)]
    angles = [a for a in angles if abs(a) <= settings.max_skew_degrees]
    return float(np.median(angles)) if angles else 0.0


def rotate(image: np.ndarray, degrees: float, border_value) -> np.ndarray:
    if abs(degrees) < 0.05:
        return image
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=border_value)


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _lab_channels(bgr: np.ndarray, median_ksize: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lightness = lab[..., 0].astype(np.float32) * (100 / 255)  # OpenCV stores L as 0..255
    a = cv2.medianBlur(lab[..., 1], median_ksize).astype(np.float32) - 128
    b = cv2.medianBlur(lab[..., 2], median_ksize).astype(np.float32) - 128
    return lightness, a, b


def barcode_views(gray: np.ndarray, settings: PreprocessSettings) -> list[np.ndarray]:
    """Several renditions of the page; zbar is tried on each because no single one wins on every scan."""
    blurred = cv2.GaussianBlur(gray, (0, 0), 2)
    sharpened = cv2.addWeighted(gray, 1.6, blurred, -0.6, 0)
    upscaled = cv2.resize(gray, None, fx=settings.barcode_upscale, fy=settings.barcode_upscale, interpolation=cv2.INTER_CUBIC)
    downscaled = cv2.resize(gray, None, fx=settings.barcode_downscale, fy=settings.barcode_downscale, interpolation=cv2.INTER_AREA)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [gray, sharpened, upscaled, downscaled, otsu]


_CV_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def fix_orientation(image: np.ndarray, settings: PreprocessSettings) -> tuple[np.ndarray, int]:
    """Rotate pages scanned sideways / upside down. Skipped (0) when OCR isn't installed or OSD is unsure."""
    import ocr_reader  # local import: preprocessing still works (without this step) when Tesseract is missing

    if not ocr_reader.is_available():
        return image, 0
    small = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), None, fx=settings.orientation_scale,
                       fy=settings.orientation_scale, interpolation=cv2.INTER_AREA)
    degrees, confidence = ocr_reader.detect_rotation(small)
    if degrees not in _CV_ROTATIONS or confidence < settings.orientation_min_confidence:
        return image, 0
    return cv2.rotate(image, _CV_ROTATIONS[degrees]), degrees


# ── pipeline ─────────────────────────────────────────────────────────────────


def _hue_in(hue: np.ndarray, hue_range: tuple[float, float]) -> np.ndarray:
    low, high = hue_range
    return (hue >= low) & (hue <= high)


def _ink_mask(gray: np.ndarray, settings: PreprocessSettings) -> np.ndarray:
    flat = normalize_illumination(gray, settings.background_kernel_ratio)
    return cv2.bitwise_not(sauvola(flat, settings.sauvola_window, settings.sauvola_k))


def preprocess(bgr: np.ndarray, source_dpi: float | None = None, settings: PreprocessSettings = DEFAULT_SETTINGS) -> PageViews:
    """Turn one scanned page (BGR) into the per-consumer views described in the module docstring."""
    image = rescale_to_dpi(bgr, source_dpi or settings.target_dpi, settings.target_dpi)

    # 1. Fix orientation, then straighten the scan — every mask below is computed once, on the final geometry.
    image, rotation = fix_orientation(image, settings)
    skew = estimate_skew(_ink_mask(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), settings), settings)
    image = rotate(image, skew, (255, 255, 255))

    # 2. Classify colour by hue angle in the (smoothed) a*b* plane.
    lightness, a, b = _lab_channels(image, settings.chroma_median_ksize)
    chroma = np.sqrt(a * a + b * b)
    hue = np.degrees(np.arctan2(b, a)) % 360

    # 3. Yellow highlighter → paper, except for dark ink written on top of it.
    highlighter = (
        _hue_in(hue, settings.highlighter_hue_range)
        & (chroma >= settings.highlighter_chroma_min)
        & (lightness > settings.highlighter_ink_l_max)
    )
    image = image.copy()
    image[highlighter] = 255
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 4. Ink (even lighting + Sauvola), split into print / pen / stamp layers.
    ink = _ink_mask(gray, settings) > 0
    # Nobody writes in yellow: dark ink with a yellow hue is black print sitting on a marker (the smoothed
    # chroma bleeds the marker's colour into thin black strokes).
    on_marker = _hue_in(hue, settings.highlighter_hue_range)
    colored = (chroma >= settings.colored_chroma_min) & ~on_marker
    pen = ink & colored & _hue_in(hue, settings.pen_hue_range)
    stamp = ink & colored & ~pen
    black = ink & ~colored

    # 4. Remove form ruling lines from the printed layer, then clean speckles.
    black_mask = np.where(black, 255, 0).astype(np.uint8)
    horizontal, vertical = _line_masks(black_mask, settings.line_min_length_ratio)
    lines = cv2.bitwise_or(horizontal, vertical)
    text = cv2.subtract(black_mask, cv2.dilate(lines, np.ones((3, 3), np.uint8)))
    text = cv2.morphologyEx(text, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))  # re-join strokes cut by a line
    text = remove_small_components(text, settings.min_component_area)

    handwriting = remove_small_components(np.where(pen, 255, 0).astype(np.uint8), settings.min_component_area)
    stamps = remove_small_components(np.where(stamp, 255, 0).astype(np.uint8), settings.min_component_area)

    total_ink = max(int(ink.sum()), 1)
    return PageViews(
        normalized=image,
        print_binary=cv2.bitwise_not(text),
        handwriting=handwriting,
        stamps=stamps,
        lines=lines,
        barcode_views=barcode_views(gray, settings),
        skew_degrees=skew,
        stats={
            "rotation_degrees": rotation,
            "skew_degrees": round(skew, 2),
            "highlighter_px_pct": round(float(highlighter.mean() * 100), 2),
            "print_ink_pct_of_ink": round(float((text > 0).sum() / total_ink * 100), 1),
            "handwriting_pct_of_ink": round(float((handwriting > 0).sum() / total_ink * 100), 1),
            "stamp_pct_of_ink": round(float((stamps > 0).sum() / total_ink * 100), 1),
            "lines_pct_of_ink": round(float((lines > 0).sum() / total_ink * 100), 1),
        },
    )
