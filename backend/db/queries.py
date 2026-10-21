from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, String, and_, asc, cast, delete, desc, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import object_session, selectinload

from .constants import (
    FIELDS,
    FIELD_KINDS,
    ROW_KEY_FIELD,
    FIELD_STATUSES,
    FORM_COLUMN_LABELS,
    FORM_STATUSES,
    FORM_TYPES,
    MULTI_VALUE_FIELDS,
    PENDING_FORM_STATUSES,
    REVIEW_FIELD_STATUSES,
    SENDER_KINDS,
    SOURCE_LABELS,
)
from .models import ExtractedField, Form, Sender
from .session import SessionLocal
from validators import digits_only, parse_iso_like_date

# ── Validation ───────────────────────────────────────────────────────────────


def _require_in(value: Any, allowed, label: str) -> Any:
    if value not in allowed:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _manual_value(field_name: str, value: str) -> str:
    """A value set by the lab worker, in the stored format: dates as DD/MM/YYYY (as extraction stores them)."""
    if FIELD_KINDS[field_name] == "date":
        parsed = parse_iso_like_date(value)
        if parsed is not None:
            return parsed.strftime("%d/%m/%Y")
    return value


# ── Serialization (the only place ORM rows become dicts) ─────────────────────

# Per-source evidence columns (JSON text). They are heavy, so they're only returned with with_sources=True.
SOURCE_COLUMNS = ("llm_result", "barcode_result", "ocr_result", "source_errors")
_FORM_COLUMNS = [column.name for column in Form.__table__.columns if column.name not in SOURCE_COLUMNS]
_FIELD_COLUMNS = [column.name for column in ExtractedField.__table__.columns]


def _from_json(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


def _to_json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def field_to_dict(row: ExtractedField) -> dict[str, Any]:
    data = {name: getattr(row, name) for name in _FIELD_COLUMNS}
    data["evidence"] = _from_json(row.evidence)
    return data


def _commitment_duplicates(session, form_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Commitment numbers of these forms that another form has too (compared as digits), per form id.
    The commitment number is the export's row key, so a repeat is flagged — never blocked: the lab worker decides.
    Scans every commitment value in the DB (one small indexed query; fine at the lab's volume)."""
    if not form_ids:
        return {}
    value = _field_display_value()
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
    """duplicates: precomputed by the caller for a batch (see list_forms); otherwise looked up for this form."""
    data = {name: getattr(form, name) for name in _FORM_COLUMNS}
    if with_fields:
        data["fields"] = [field_to_dict(row) for row in form.extracted_fields]
        if duplicates is None:
            duplicates = _commitment_duplicates(object_session(form), [form.id])[form.id]
        data["duplicates"] = duplicates
    if with_sources:
        data["sources"] = {name: _from_json(getattr(form, name)) for name in SOURCE_COLUMNS}
    return data


# ── Forms ────────────────────────────────────────────────────────────────────


def add_form(source_file: str, file_hash: str, page_number: int, image_path: str) -> int:
    if not source_file or not file_hash or not image_path:
        raise ValueError("source_file, file_hash and image_path are required.")
    if not isinstance(page_number, int):
        raise ValueError("page_number must be an integer.")

    with SessionLocal() as session, session.begin():
        form = Form(source_file=source_file, file_hash=file_hash, page_number=page_number, image_path=image_path, status="uploaded")
        session.add(form)
        session.flush()
        return int(form.id)


def find_forms_by_hash(file_hash: str) -> list[dict[str, Any]]:
    if not file_hash:
        raise ValueError("file_hash is required.")
    with SessionLocal() as session:
        rows = session.execute(select(Form).where(Form.file_hash == file_hash).order_by(Form.id)).scalars().all()
        return [form_to_dict(form, with_fields=False) for form in rows]


def get_form(form_id: int, *, with_sources: bool = False) -> dict[str, Any] | None:
    with SessionLocal() as session:
        form = session.get(Form, form_id, options=[selectinload(Form.extracted_fields)])
        return form_to_dict(form, with_sources=with_sources) if form is not None else None


def delete_forms_by_hash(file_hash: str) -> int:
    if not file_hash:
        raise ValueError("file_hash is required.")
    with SessionLocal() as session, session.begin():
        return int(session.execute(delete(Form).where(Form.file_hash == file_hash)).rowcount or 0)


def set_form_status(form_id: int, status: str, error: str | None = None) -> None:
    _require_in(status, FORM_STATUSES, "form status")
    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id)
        if form is None:
            raise ValueError(f"Form {form_id} not found.")
        form.status = status
        form.error = error


# ── Extraction queue ─────────────────────────────────────────────────────────


def claim_next_form() -> dict[str, Any] | None:
    """Atomically move the oldest queued form to 'processing' and return it (None when the queue is empty)."""
    for _ in range(10):
        with SessionLocal() as session, session.begin():
            candidate = session.execute(
                select(Form).where(Form.status == "uploaded").order_by(Form.id).limit(1)
            ).scalar_one_or_none()
            if candidate is None:
                return None
            claimed = session.execute(
                update(Form).where(Form.id == candidate.id, Form.status == "uploaded").values(status="processing", error=None)
            ).rowcount
            if claimed == 1:
                candidate.status = "processing"
                return form_to_dict(candidate, with_fields=False)
    return None


def requeue_stale_processing() -> int:
    """Forms left in 'processing' by a crashed/stopped server go back to the queue."""
    with SessionLocal() as session, session.begin():
        return int(session.execute(update(Form).where(Form.status == "processing").values(status="uploaded")).rowcount or 0)


def return_to_queue(form_id: int) -> None:
    """Put a claimed form back in the queue (e.g. the model was rate-limited, not the form's fault)."""
    with SessionLocal() as session, session.begin():
        session.execute(update(Form).where(Form.id == form_id, Form.status == "processing").values(status="uploaded"))


def requeue_form(form_id: int) -> None:
    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id)
        if form is None:
            raise ValueError(f"Form {form_id} not found.")
        if form.status in PENDING_FORM_STATUSES:
            return
        form.status = "uploaded"
        form.error = None


# ── Extracted fields ─────────────────────────────────────────────────────────

_WRITABLE_FIELD_KEYS = {
    "value", "llm_value", "barcode_value", "ocr_value", "status", "confidence", "reason",
    "box_source", "page", "x", "y", "width", "height",
}


def save_source_results(form_id: int, **results: Any) -> None:
    """Persist raw results of individual sources (llm_result / barcode_result / ocr_result / source_errors).

    Called per source as soon as it finishes, so a later failure of another source can't discard them.
    """
    unknown = set(results) - set(SOURCE_COLUMNS)
    if unknown:
        raise ValueError(f"Unknown source columns: {sorted(unknown)}")
    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id)
        if form is None:
            raise ValueError(f"Form {form_id} not found.")
        for column, value in results.items():
            setattr(form, column, _to_json(value))


def _recalculate_form_status(session, form: Form, keep_pending: bool = False) -> None:
    """A form is approved once no field needs a human decision.
    keep_pending: a manual edit on a form still in the extraction queue must not take it out of the queue."""
    if keep_pending and form.status in PENDING_FORM_STATUSES:
        return
    needs_review = any(row.status in REVIEW_FIELD_STATUSES for row in form.extracted_fields)
    form.status = "extracted" if needs_review or not form.extracted_fields else "approved"


def save_extraction(form_id: int, fields: list[dict[str, Any]], form_type: str | None = None) -> None:
    """Replace the machine-extracted fields of a form. Fields a human already decided on (confirmed or
    corrected) are kept as-is, so re-extraction / re-verification never discards a human decision.

    Raw source results are stored separately via save_source_results().
    """
    if form_type is not None:
        _require_in(form_type, FORM_TYPES, "form_type")

    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id, options=[selectinload(Form.extracted_fields)])
        if form is None:
            raise ValueError(f"Form {form_id} not found.")

        human_corrected = {
            row.field_name for row in form.extracted_fields if row.status == "confirmed" or row.corrected_value is not None
        }
        for row in list(form.extracted_fields):
            if row.field_name not in human_corrected:
                form.extracted_fields.remove(row)

        for entry in fields:
            name = _require_in(entry.get("field_name"), FIELDS, "field_name")
            if name in human_corrected:
                continue
            _require_in(entry.get("status", "unverified"), FIELD_STATUSES, "field status")
            form.extracted_fields.append(
                ExtractedField(
                    field_name=name,
                    evidence=_to_json(entry.get("evidence")),
                    **{key: entry[key] for key in _WRITABLE_FIELD_KEYS if key in entry},
                )
            )

        form.form_type = form_type
        form.error = None
        session.flush()
        _recalculate_form_status(session, form)


def add_manual_field(
    form_id: int,
    field_name: str,
    value: str,
    *,
    replace: bool = False,
    box: dict[str, float] | None = None,
    picked_from: str | None = None,
) -> dict[str, Any]:
    """A value set by the lab worker — typed, or picked from a number a source found on the page (then `box` is
    where it is and `picked_from` which source read it, so the page highlight keeps working). It counts as
    confirmed and survives re-extraction. A single-value field takes it only when empty, unless `replace`."""
    _require_in(field_name, FIELDS, "field_name")
    value = (value or "").strip()
    if not value:
        raise ValueError("Value cannot be empty.")
    value = _manual_value(field_name, value)
    if picked_from is not None:
        _require_in(picked_from, SOURCE_LABELS, "source")
    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id, options=[selectinload(Form.extracted_fields)])
        if form is None:
            raise LookupError(f"Form {form_id} not found.")
        existing = [row for row in form.extracted_fields if row.field_name == field_name]
        has_value = any(row.status != "not_found" for row in existing)
        if field_name not in MULTI_VALUE_FIELDS and has_value and not replace:
            raise ValueError(f"{field_name} already has a value — edit it instead.")
        for row in existing:
            # The "not found" placeholder always goes; a single-value field's old value goes when replaced.
            if row.status == "not_found" or (replace and field_name not in MULTI_VALUE_FIELDS):
                form.extracted_fields.remove(row)
        coordinates = {key: float(box[key]) for key in ("x", "y", "width", "height")} if box else {}
        form.extracted_fields.append(ExtractedField(
            field_name=field_name, value=value, corrected_value=value, status="confirmed",
            evidence=_to_json({"manual": True, **({"picked_from": picked_from} if picked_from else {})}),
            box_source=picked_from if box else None,
            **coordinates,
        ))
        session.flush()
        _recalculate_form_status(session, form, keep_pending=True)
        return form_to_dict(form, with_sources=True)


def delete_field(form_id: int, field_id: int) -> dict[str, Any]:
    """Remove a value the lab worker rejected. (A later re-extraction may read it again; that's intended —
    machine readings are evidence, the worker decides again.)"""
    with SessionLocal() as session, session.begin():
        form = session.get(Form, form_id, options=[selectinload(Form.extracted_fields)])
        row = next((r for r in form.extracted_fields if r.id == field_id), None) if form else None
        if row is None:
            raise LookupError(f"Field {field_id} not found for form {form_id}.")
        form.extracted_fields.remove(row)
        session.flush()
        _recalculate_form_status(session, form, keep_pending=True)
        return form_to_dict(form, with_sources=True)


def confirm_field(form_id: int, field_id: int, corrected_value: str | None) -> dict[str, Any]:
    """Human approval of one field value (optionally corrected)."""
    with SessionLocal() as session, session.begin():
        row = session.execute(
            select(ExtractedField).where(ExtractedField.id == field_id, ExtractedField.form_id == form_id)
        ).scalar_one_or_none()
        if row is None:
            raise LookupError(f"Field {field_id} not found for form {form_id}.")

        if corrected_value is not None:
            corrected_value = _manual_value(row.field_name, corrected_value.strip())
        if corrected_value is not None and corrected_value != row.value:
            row.corrected_value = corrected_value
            row.value = corrected_value
        row.status = "confirmed"
        session.flush()

        _recalculate_form_status(session, row.form, keep_pending=True)
        return form_to_dict(row.form, with_sources=True)


# ── Listing (paging, filtering, sorting — all in SQL) ────────────────────────

FORM_SORT_COLUMNS = {name: getattr(Form, name) for name in FORM_COLUMN_LABELS}


def _field_display_value():
    return func.coalesce(ExtractedField.corrected_value, ExtractedField.value, ExtractedField.llm_value)


def _field_matches(field_name: str | None, needle: str):
    conditions = [ExtractedField.form_id == Form.id, _field_display_value().ilike(f"%{needle}%")]
    if field_name is not None:
        conditions.append(ExtractedField.field_name == field_name)
    return exists().where(and_(*conditions))


@dataclass
class FormFilters:
    status: str | None = None
    query: str | None = None
    column_filters: dict[str, str] = field(default_factory=dict)
    sort_by: str = "id"
    sort_dir: str = "desc"


def _apply_filters(stmt: Select, filters: FormFilters) -> Select:
    if filters.status:
        stmt = stmt.where(Form.status == _require_in(filters.status, FORM_STATUSES, "form status"))

    needle = (filters.query or "").strip()
    if needle:
        stmt = stmt.where(or_(Form.source_file.ilike(f"%{needle}%"), _field_matches(None, needle)))

    for key, raw in filters.column_filters.items():
        value = (raw or "").strip()
        if not value:
            continue
        if key in FORM_SORT_COLUMNS:
            stmt = stmt.where(cast(FORM_SORT_COLUMNS[key], String).ilike(f"%{value}%"))
        elif key in FIELDS:
            stmt = stmt.where(_field_matches(key, value))
        else:
            raise ValueError(f"Unknown filter column: {key!r}")
    return stmt


def _sort_expression(filters: FormFilters):
    direction = desc if filters.sort_dir == "desc" else asc
    if filters.sort_by in FORM_SORT_COLUMNS:
        return direction(FORM_SORT_COLUMNS[filters.sort_by])
    if filters.sort_by in FIELDS:
        first_value = (
            select(func.min(_field_display_value()))
            .where(ExtractedField.form_id == Form.id, ExtractedField.field_name == filters.sort_by)
            .scalar_subquery()
        )
        return direction(first_value)
    raise ValueError(f"Unknown sort column: {filters.sort_by!r}")


def list_forms(filters: FormFilters, limit: int, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Return one page of forms (with fields) and the total number of matching forms."""
    if limit <= 0 or offset < 0:
        raise ValueError("limit must be positive and offset non-negative.")

    with SessionLocal() as session:
        total = session.execute(_apply_filters(select(func.count(Form.id)), filters)).scalar_one()
        stmt = (
            _apply_filters(select(Form), filters)
            .options(selectinload(Form.extracted_fields))
            .order_by(_sort_expression(filters), desc(Form.id))
            .limit(limit)
            .offset(offset)
        )
        rows = session.execute(stmt).scalars().all()
        duplicates = _commitment_duplicates(session, [form.id for form in rows])
        return [form_to_dict(form, duplicates=duplicates[form.id]) for form in rows], int(total)


def forms_summary() -> dict[str, Any]:
    with SessionLocal() as session:
        by_status = dict(session.execute(select(Form.status, func.count(Form.id)).group_by(Form.status)).all())
        review_fields = session.execute(
            select(func.count(ExtractedField.id)).where(ExtractedField.status.in_(REVIEW_FIELD_STATUSES))
        ).scalar_one()
    counts = {status: int(by_status.get(status, 0)) for status in FORM_STATUSES}
    return {
        "total": sum(counts.values()),
        "by_status": counts,
        "pending": sum(counts[status] for status in PENDING_FORM_STATUSES),
        "fields_to_review": int(review_fields),
    }


# ── Senders ──────────────────────────────────────────────────────────────────


def list_senders() -> list[tuple[str, str]]:
    with SessionLocal() as session:
        rows = session.execute(select(Sender).order_by(Sender.name)).scalars().all()
        return [(row.name, row.kind) for row in rows]


def add_sender(name: str, kind: str) -> int:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Sender name cannot be empty.")
    _require_in(kind, SENDER_KINDS, "sender kind")

    with SessionLocal() as session, session.begin():
        sender = Sender(name=normalized_name, kind=kind)
        session.add(sender)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ValueError(f"Sender {normalized_name!r} already exists.") from exc
        return int(sender.id)
