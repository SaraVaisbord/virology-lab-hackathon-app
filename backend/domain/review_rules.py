"""What the lab worker's decisions mean for a field and a form.

Pure rules over field rows: `row` is anything with the ExtractedField attributes (value, corrected_value, llm_value,
barcode_value, ocr_value, status, reason). Rejected values are {field_name: [value, ...]}.
"""

from __future__ import annotations

from typing import Any

from domain.validators import match_key, parse_iso_like_date
from domain.vocabulary import FIELD_KINDS, REASONS, REVIEW_FIELD_STATUSES

# What each source read for a field, by row attribute.
SOURCE_VALUE_COLUMNS = {"llm": "llm_value", "barcode": "barcode_value", "ocr": "ocr_value"}


def manual_value(field_name: str, value: str) -> str:
    """A value set by the lab worker, in the stored format: dates as DD/MM/YYYY (as extraction stores them)."""
    if FIELD_KINDS[field_name] == "date":
        parsed = parse_iso_like_date(value)
        if parsed is not None:
            return parsed.strftime("%d/%m/%Y")
    return value


# ── Values the lab worker rejected (deleted) — never put back by re-extraction ─


def is_rejected(rejected: dict[str, list[str]], field_name: str, value: Any) -> bool:
    key = match_key(field_name, value)
    return bool(key) and any(match_key(field_name, old) == key for old in rejected.get(field_name, []))


def with_rejection(rejected: dict[str, list[str]], field_name: str, value: Any, is_rejected_now: bool) -> dict[str, list[str]]:
    """The rejected values with this value added (or, when the worker sets it again, removed); empty lists dropped."""
    values = dict(rejected)
    kept = [old for old in values.get(field_name, []) if match_key(field_name, old) != match_key(field_name, value)]
    values[field_name] = kept + ([str(value)] if is_rejected_now else [])
    return {name: items for name, items in values.items() if items}


def empty_field_reason(rejected: dict[str, list[str]], field_name: str) -> str:
    """A field left without a value still needs a decision: 'not found' (the worker confirms it empty or fills it)."""
    return REASONS["rejected_by_worker" if rejected.get(field_name) else "not_found"]


# ── Field values ─────────────────────────────────────────────────────────────


def display_value(row) -> str | None:
    """The value the lab worker sees for a field (as the UI and the table show it)."""
    return row.corrected_value or row.value or row.llm_value


def source_values(row) -> dict[str, str]:
    """What each source read for this field row: {source: value}, sources that read nothing left out."""
    if row is None:
        return {}
    return {source: getattr(row, column) for source, column in SOURCE_VALUE_COLUMNS.items() if getattr(row, column)}


def value_origin(row, evidence: dict[str, Any] | None) -> str:
    """Where a field's current value came from (a VALUE_ORIGINS key). evidence: the row's evidence, parsed."""
    if row is None:
        return "machine"
    if row.status == "not_found":  # emptied by the worker deleting its value, or simply not found by the extraction
        return "manual" if row.reason == REASONS["rejected_by_worker"] else "machine"
    if row.status != "confirmed":
        return "machine"
    manual = row.corrected_value is not None or (evidence or {}).get("manual")
    return "manual" if manual else "machine_confirmed"


# ── Form status ──────────────────────────────────────────────────────────────


def reviewed_form_status(field_statuses: list[str]) -> str:
    """A form is approved once no field needs a human decision (and it has fields at all)."""
    needs_review = any(status in REVIEW_FIELD_STATUSES for status in field_statuses)
    return "extracted" if needs_review or not field_statuses else "approved"
