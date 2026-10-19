"""Local extractor rules on synthetic OCR words (no Tesseract needed). Each case is a pitfall seen on the samples."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

import local_extractor
from local_extractor import DEFAULT_SETTINGS as S, _matches, normalize_date
from ocr_reader import OcrWord
from preprocessing import PageViews

LINE_H = 0.015


def _word(text, x, y, width=0.06, confidence=90):
    return OcrWord(text=text, confidence=confidence, x=x, y=y, width=width, height=LINE_H, line_key=(0, 0, 0))


@pytest.fixture
def views():
    blank = np.full((100, 100, 3), 255, np.uint8)
    return PageViews(normalized=blank, print_binary=blank[..., 0], handwriting=blank[..., 0], stamps=blank[..., 0], lines=blank[..., 0])


@pytest.fixture(autouse=True)
def _no_real_ocr(monkeypatch):
    monkeypatch.setattr(local_extractor, "_targeted_tokens", lambda views, label, settings: [])
    monkeypatch.setattr(local_extractor, "_sticker_words", lambda views, barcodes, settings: [])


def _extract(views, words, barcodes=None):
    result = local_extractor.extract(views, barcodes or [], words=words)
    return {(c.field, c.value) for c in result.candidates if c.rank == 0}, result


def test_value_left_of_label_on_the_same_line(views):
    # RTL: "מקרה: 12043017" — the label is on the right, the value to its left
    pairs, _ = _extract(views, [_word("מקרה:", 0.50, 0.30), _word("12043017", 0.38, 0.30, 0.1)])
    assert pairs == {("central_number", "12043017")}


def test_value_below_the_label(views):
    pairs, _ = _extract(views, [_word("מספר", 0.27, 0.36), _word("התחייבות", 0.20, 0.36), _word("2646", 0.25, 0.385)])
    assert pairs == {("commitment_number", "2646")}


def test_glued_label_and_number_with_ocr_misread(views):
    # OCR read "מקרה" as "מסרה" and glued it to the number
    pairs, _ = _extract(views, [_word("מסרה:12043017", 0.23, 0.29, 0.13)])
    assert pairs == {("central_number", "12043017")}


def test_fuzzy_matching_rejects_other_words():
    assert _matches("מסרה", "מקרה", S)  # one substituted letter
    assert _matches("ההתחייבות", "התחייבות", S)  # Hebrew prefix
    assert not _matches("מרכזית", "מרכזי", S)  # feminine form — a pharmacy, not "central number"
    assert not _matches("מרכז", "מרכזי", S)  # "centre"


def test_form_title_is_not_a_commitment_label_unless_numbered(views):
    title = [_word("טופס", 0.60, 0.10), _word("התחייבות", 0.50, 0.10), _word("לבדיקת", 0.40, 0.10)]
    pairs, result = _extract(views, title + [_word("123456", 0.30, 0.10)])
    assert pairs == set() and not result.labels
    numbered = [_word("טופס", 0.60, 0.10), _word("התחייבות", 0.50, 0.10), _word("מס'", 0.42, 0.10), _word("58153", 0.33, 0.10)]
    pairs, _ = _extract(views, numbered)
    assert pairs == {("commitment_number", "58153")}


def test_instruction_line_is_not_a_label(views):
    words = [_word("נא", 0.80, 0.85), _word("לציין", 0.72, 0.85), _word("מספר", 0.64, 0.85), _word("ההתחייבות", 0.55, 0.85), _word("555555", 0.45, 0.85)]
    pairs, _ = _extract(views, words)
    assert pairs == set()


def test_negative_labels_block_catalog_and_phone_numbers(views):
    words = [_word("מקרה:", 0.50, 0.30), _word('מק"ט', 0.44, 0.30, 0.04), _word("12017572", 0.33, 0.30, 0.1),
             _word("טל':", 0.50, 0.50), _word("03-5078369", 0.38, 0.50, 0.1)]
    pairs, result = _extract(views, words)
    assert pairs == set()
    assert all(u["value"] != "12017572" for u in result.unassigned_numbers)  # negative numbers aren't candidates


def test_id_needs_eight_digits_and_a_valid_check_digit(views):
    label = _word("ת.ז", 0.50, 0.40)
    assert _extract(views, [label, _word("100826", 0.40, 0.40)])[0] == set()  # 6 digits, passes checksum by chance
    assert _extract(views, [label, _word("123456789", 0.38, 0.40, 0.1)])[0] == set()  # bad check digit
    assert _extract(views, [label, _word("000000018", 0.38, 0.40, 0.1)])[0] == {("id_number", "000000018")}


def test_received_date_prefers_specific_label_and_rejects_old_dates(views):
    recent = (date.today() - timedelta(days=3)).strftime("%d.%m.%y")
    other = (date.today() - timedelta(days=10)).strftime("%d.%m.%y")
    words = [
        _word("תאריך", 0.50, 0.20), _word(other, 0.42, 0.20),  # generic label, closer
        _word("ת.קבלה:", 0.50, 0.60), _word(recent, 0.40, 0.60),  # specific label
        _word("תאריך", 0.50, 0.90), _word("07/01/2020", 0.40, 0.90, 0.08),  # old printed form-version date
    ]
    pairs, result = _extract(views, words)
    assert pairs == {("received_date", normalize_date(recent))}
    assert all(c.value != "07/01/2020" for c in result.candidates)


def test_barcode_next_to_label_is_a_candidate_and_numbers_are_never_dropped(views):
    barcode = {"data": "2646", "type": "CODE39", "x": 0.25, "y": 0.39, "width": 0.08, "height": 0.03}
    words = [_word("מספר", 0.27, 0.36), _word("התחייבות", 0.20, 0.36), _word("947768", 0.70, 0.70)]
    pairs, result = _extract(views, words, [barcode])
    assert pairs == {("commitment_number", "2646")}
    assert any(u["value"] == "947768" for u in result.unassigned_numbers)  # unlabeled — kept, not assigned


def test_normalize_date():
    assert normalize_date("27.8.26") == "27/08/2026"
    assert normalize_date("27-08-2026") == "27/08/2026"
    assert normalize_date("32.08.26") is None
