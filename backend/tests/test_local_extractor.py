"""Local extractor rules on synthetic OCR words (no Tesseract needed). Each case is a pitfall seen on the samples."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from integrations.imaging.preprocessing import PageViews
from integrations.ocr import local_extractor
from integrations.ocr.base import OcrWord
from integrations.ocr.local_extractor import DEFAULT_SETTINGS as S
from integrations.ocr.local_extractor import LocalExtractor, _matches, normalize_date

LINE_H = 0.015


def _word(text, x, y, width=0.06, confidence=90):
    return OcrWord(text=text, confidence=confidence, x=x, y=y, width=width, height=LINE_H, line_key=(0, 0, 0))


@pytest.fixture
def views():
    blank = np.full((100, 100, 3), 255, np.uint8)
    return PageViews(normalized=blank, print_binary=blank[..., 0], handwriting=blank[..., 0], stamps=blank[..., 0], lines=blank[..., 0])


class _NoOcr:
    """The page words are given to each test; re-reads (next to a label, around a barcode) find nothing."""

    def is_available(self):
        return True

    def read_words(self, image, psm=11, languages=None, extra_config=None):
        return []

    def detect_rotation(self, image):
        return 0, 0.0


def _extract(views, words, barcodes=None):
    result = LocalExtractor(_NoOcr(), received_date_max_age_days=365).extract(views, barcodes or [], words=words)
    return {(c.field, c.value) for c in result.candidates if c.rank == 0}, result


def test_value_left_of_label_on_the_same_line(views):
    # RTL: "מרכזי: 12043017" — the label is on the right, the value to its left
    pairs, _ = _extract(views, [_word("מרכזי:", 0.50, 0.30), _word("12043017", 0.38, 0.30, 0.1)])
    assert pairs == {("central_number", "12043017")}


def test_value_below_the_label(views):
    pairs, _ = _extract(views, [_word("מספר", 0.27, 0.36), _word("התחייבות", 0.20, 0.36), _word("2646", 0.25, 0.385)])
    assert pairs == {("commitment_number", "2646")}


def test_glued_label_and_number_with_ocr_misread(views):
    # OCR read "מרכזי" as "מרכדי" and glued it to the number
    pairs, _ = _extract(views, [_word("מרכדי:12043017", 0.23, 0.29, 0.13)])
    assert pairs == {("central_number", "12043017")}


def test_fuzzy_matching_rejects_other_words():
    assert _matches("מרכדי", "מרכזי", S)  # one substituted letter
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
    words = [_word("מרכזי:", 0.50, 0.30), _word('מק"ט', 0.44, 0.30, 0.04), _word("12017572", 0.33, 0.30, 0.1),
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


# ── lab definitions (2026-10-20): row key, Leumit, central number, received date ──


def _recent(days=10):
    return (date.today() - timedelta(days=days)).strftime("%d/%m/%Y")


def test_case_number_is_not_a_central_number(views):
    # "מקרה" is the referring institution's case number — the lab doesn't use it; the number stays unassigned
    pairs, result = _extract(views, [_word("מקרה:", 0.50, 0.30), _word("12043017", 0.38, 0.30, 0.1)])
    assert pairs == set()
    assert any(n["value"] == "12043017" for n in result.unassigned_numbers)


def test_requisition_number_is_a_commitment_but_a_heading_is_not(views):
    pairs, _ = _extract(views, [_word("מס'", 0.56, 0.30, 0.04), _word("דרישה:", 0.50, 0.30), _word("58153", 0.40, 0.30, 0.08)])
    assert pairs == {("commitment_number", "58153")}
    heading, _ = _extract(views, [_word("דרישה", 0.56, 0.30), _word("לבדיקה", 0.48, 0.30), _word("58153", 0.38, 0.30, 0.08)])
    assert heading == set()


def test_sample_label_is_a_commitment_only_on_leumit_forms(views):
    words = [_word("דגימה:", 0.50, 0.30), _word("7712345", 0.40, 0.30, 0.08)]
    leumit_pairs, leumit = _extract(views, [_word("לאומית", 0.80, 0.05)] + words)
    assert leumit.form_type == "leumit"
    assert leumit_pairs == {("commitment_number", "7712345")}
    other_pairs, other = _extract(views, words)
    assert other.form_type is None and other_pairs == set()


def test_phone_fax_department_numbers_are_dropped_but_not_the_rest_of_the_line(views):
    # Maccabi header: "דרישה:606/50364186  ת.דרישה: …  טל: 04-6161999  מחלקה 1234" — "ת.דרישה" is not "ת.ד"
    words = [_word("דרישה:", 0.90, 0.20), _word("50364186", 0.80, 0.20, 0.08), _word("ת.דרישה:", 0.70, 0.20),
             _word("טל:", 0.55, 0.20, 0.03), _word("04-6161999", 0.44, 0.20, 0.1),
             _word("מחלקה", 0.30, 0.20), _word("12345", 0.22, 0.20, 0.06), _word("0527736881", 0.05, 0.50, 0.1)]
    pairs, result = _extract(views, words)
    assert pairs == {("commitment_number", "50364186")}
    assert [n["value"] for n in result.unassigned_numbers] == []  # phone, department, mobile — all gone


def test_irrelevant_numbers_are_removed_from_the_ai_inventory():
    llm = {"all_numbers": [{"value": "03-5303030", "label": ""}, {"value": "4069600", "label": "לאינטר פקס"},
                           {"value": "13872", "label": "מ.ר."}, {"value": "947550", "label": "מרכזי"},
                           {"value": "001122334", "label": "ת.ז"}]}
    kept = local_extractor.drop_irrelevant_numbers(llm)["all_numbers"]
    assert [n["value"] for n in kept] == ["947550", "001122334"]  # an ID is not mistaken for a phone


def test_sample_label_is_a_commitment_where_the_page_says_so(views):
    # Rambam: "שימו לב! מספר הדגימה מהווה מספר התחייבות" — and the statement itself is not a label
    declaration = [_word("מספר", 0.60, 0.60), _word("הדגימה", 0.52, 0.60), _word("מהווה", 0.45, 0.60),
                   _word("מספר", 0.38, 0.60), _word("התחייבות", 0.29, 0.60, 0.08), _word("87299", 0.20, 0.60, 0.06)]
    words = [_word("דגימה:", 0.50, 0.30), _word("944000351", 0.38, 0.30, 0.1)]
    pairs, result = _extract(views, declaration + words)
    assert result.sample_is_commitment and result.form_type is None
    assert pairs == {("commitment_number", "944000351")}  # not 87299 next to the statement


def test_received_date_is_the_one_under_the_central_number(views):
    under, elsewhere = _recent(5), _recent(30)
    _, result = _extract(views, [
        _word("מרכזי:", 0.50, 0.30), _word("12043017", 0.38, 0.30, 0.1),
        _word(under, 0.40, 0.34, 0.1),  # stamped / handwritten right under the sticker
        _word("תאריך:", 0.50, 0.70), _word(elsewhere, 0.38, 0.70, 0.1),  # another date on the form
    ])
    best = next(c for c in result.candidates if c.field == "received_date" and c.rank == 0)
    assert best.value == under and best.anchor == "central_number" and "12043017" in best.label
    assert any(c.field == "received_date" and c.value == elsewhere for c in result.candidates)  # kept as an option
