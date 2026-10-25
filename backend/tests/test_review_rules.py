"""The review rules in domain/review_rules.py, without a database (rows are plain objects)."""

from __future__ import annotations

from types import SimpleNamespace

from domain import review_rules
from domain.vocabulary import REASONS


def _row(status="unverified", value=None, corrected_value=None, llm_value=None, barcode_value=None, ocr_value=None, reason=None):
    return SimpleNamespace(status=status, value=value, corrected_value=corrected_value, llm_value=llm_value,
                           barcode_value=barcode_value, ocr_value=ocr_value, reason=reason)


def test_manual_dates_are_stored_like_extracted_dates():
    assert review_rules.manual_value("received_date", "2026-08-27") == "27/08/2026"
    assert review_rules.manual_value("commitment_number", "2026-08-27") == "2026-08-27"


def test_rejected_values_match_by_digits_and_can_be_taken_back():
    rejected = review_rules.with_rejection({}, "commitment_number", "47-381", True)
    assert rejected == {"commitment_number": ["47-381"]}
    assert review_rules.is_rejected(rejected, "commitment_number", "47381")
    assert review_rules.with_rejection(rejected, "commitment_number", "47381", False) == {}
    assert review_rules.empty_field_reason(rejected, "commitment_number") == REASONS["rejected_by_worker"]
    assert review_rules.empty_field_reason({}, "commitment_number") == REASONS["not_found"]


def test_value_origin():
    assert review_rules.value_origin(None, None) == "machine"
    assert review_rules.value_origin(_row("verified", value="1"), None) == "machine"
    assert review_rules.value_origin(_row("confirmed", value="1"), {}) == "machine_confirmed"
    assert review_rules.value_origin(_row("confirmed", value="2", corrected_value="2"), {}) == "manual"
    assert review_rules.value_origin(_row("confirmed", value="2"), {"manual": True}) == "manual"
    assert review_rules.value_origin(_row("not_found", reason=REASONS["rejected_by_worker"]), None) == "manual"


def test_display_and_source_values():
    row = _row(value="1", llm_value="1", barcode_value="1")
    assert review_rules.display_value(row) == "1"
    assert review_rules.display_value(_row(corrected_value="2", value="1")) == "2"
    assert review_rules.source_values(row) == {"llm": "1", "barcode": "1"}


def test_form_is_approved_only_when_nothing_needs_review():
    assert review_rules.reviewed_form_status(["verified", "confirmed"]) == "approved"
    assert review_rules.reviewed_form_status(["verified", "uncertain"]) == "extracted"
    assert review_rules.reviewed_form_status([]) == "extracted"
