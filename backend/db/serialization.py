"""ORM rows ⇄ plain data: the only place ORM rows become dicts, and the JSON columns are read or written."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from db.models import ExtractedField, Form
from domain import review_rules
from domain.validators import digits_only
from domain.vocabulary import PENDING_FORM_STATUSES, ROW_KEY_FIELD

# Per-source evidence columns (JSON text). They are heavy, so they're only returned with with_sources=True.
SOURCE_COLUMNS = ("llm_result", "barcode_result", "ocr_result", "source_errors")
_FORM_COLUMNS = [column.name for column in Form.__table__.columns if column.name not in SOURCE_COLUMNS]
_FIELD_COLUMNS = [column.name for column in ExtractedField.__table__.columns]


def from_json(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


def to_json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


# ── Rejected values of a form (JSON column) ──────────────────────────────────


def rejected(form: Form) -> dict[str, list[str]]:
    return from_json(form.rejected_values) or {}


def mark_rejected(form: Form, field_name: str, value: Any, is_rejected_now: bool) -> None:
    """Add the value to (or, when the worker sets it again, remove it from) the form's rejected values."""
    values = review_rules.with_rejection(rejected(form), field_name, value, is_rejected_now)
    form.rejected_values = to_json(values) if values else None


def empty_field(form: Form, field_name: str) -> ExtractedField:
    """The 'not found' row of a field left without a value — it still needs the lab worker's decision."""
    return ExtractedField(field_name=field_name, status="not_found", reason=review_rules.empty_field_reason(rejected(form), field_name))


def value_origin(row: ExtractedField | None) -> str:
    return review_rules.value_origin(row, from_json(row.evidence) if row is not None else None)


def recalculate_form_status(form: Form, keep_pending: bool = False) -> None:
    """keep_pending: a manual edit on a form still in the extraction queue must not take it out of the queue."""
    if keep_pending and form.status in PENDING_FORM_STATUSES:
        return
    form.status = review_rules.reviewed_form_status([row.status for row in form.extracted_fields])


# ── Rows → dicts ─────────────────────────────────────────────────────────────


def field_display_value():
    """SQL expression of the value the lab worker sees (as review_rules.display_value)."""
    return func.coalesce(ExtractedField.corrected_value, ExtractedField.value, ExtractedField.llm_value)


def field_to_dict(row: ExtractedField) -> dict[str, Any]:
    data = {name: getattr(row, name) for name in _FIELD_COLUMNS}
    data["evidence"] = from_json(row.evidence)
    return data


def commitment_duplicates(session: Session, form_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Commitment numbers of these forms that another form has too (compared as digits), per form id.
    The commitment number is the export's row key, so a repeat is flagged — never blocked: the lab worker decides.
    Scans every commitment value in the DB (one small indexed query; fine at the lab's volume)."""
    if not form_ids:
        return {}
    value = field_display_value()
    rows = session.execute(
        select(ExtractedField.id, ExtractedField.form_id, value, ExtractedField.x, ExtractedField.y, ExtractedField.width,
               ExtractedField.height, ExtractedField.box_source, Form.source_file, Form.page_number, Form.status)
        .join(Form, Form.id == ExtractedField.form_id)
        .where(ExtractedField.field_name == ROW_KEY_FIELD, value.is_not(None))
    ).all()
    by_key: dict[str, list] = {}
    for row in rows:
        if digits_only(row[2]):
            by_key.setdefault(digits_only(row[2]), []).append(row)

    wanted = set(form_ids)
    result: dict[int, list[dict[str, Any]]] = {form_id: [] for form_id in form_ids}
    for same in by_key.values():
        for mine in (row for row in same if row.form_id in wanted):
            for other in (row for row in same if row.form_id != mine.form_id):
                result[mine.form_id].append({
                    "field_id": mine.id, "value": mine[2],
                    "other_form_id": other.form_id, "other_field_id": other.id, "other_value": other[2],
                    "other_source_file": other.source_file, "other_page_number": other.page_number, "other_status": other.status,
                    "x": other.x, "y": other.y, "width": other.width, "height": other.height, "box_source": other.box_source,
                })
    return result


def form_to_dict(form: Form, *, with_fields: bool = True, with_sources: bool = False,
                 duplicates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """duplicates: precomputed by the caller for a batch (see listing); otherwise looked up for this form."""
    data = {name: getattr(form, name) for name in _FORM_COLUMNS}
    data["rejected_values"] = rejected(form)
    if with_fields:
        data["fields"] = [field_to_dict(row) for row in form.extracted_fields]
        if duplicates is None:
            duplicates = commitment_duplicates(object_session(form), [form.id])[form.id]
        data["duplicates"] = duplicates
    if with_sources:
        data["sources"] = {name: from_json(getattr(form, name)) for name in SOURCE_COLUMNS}
    return data


def require_in(value: Any, allowed, label: str) -> Any:
    if value not in allowed:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value
