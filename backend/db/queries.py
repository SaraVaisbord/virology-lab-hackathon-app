from __future__ import annotations

from typing import Any

from sqlalchemy import asc, desc, delete, select, update
from sqlalchemy.exc import IntegrityError

from .constants import FIELDS, FIELD_STATUSES, FORM_STATUSES, FORM_TYPES, SENDER_KINDS
from .models import ExtractedField, Form, Sender
from .session import SessionLocal

_UNSET = object()


def _validate_status(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _validate_form_type(form_type: str | None) -> str | None:
    if form_type is None:
        return None
    if form_type not in FORM_TYPES:
        raise ValueError(f"Invalid form_type: {form_type!r}")
    return form_type


def _validate_field_name(field_name: str) -> str:
    if field_name not in FIELDS:
        raise ValueError(f"Invalid field_name: {field_name!r}")
    return field_name


def add_form(source_file: str, file_hash: str, page_number: int, image_path: str) -> int:
    if not source_file or not file_hash or not image_path:
        raise ValueError("source_file, file_hash and image_path are required.")
    if not isinstance(page_number, int):
        raise ValueError("page_number must be an integer.")

    with SessionLocal() as session:
        with session.begin():
            form = Form(
                source_file=source_file,
                file_hash=file_hash,
                page_number=page_number,
                image_path=image_path,
                status="uploaded",
            )
            session.add(form)
            session.flush()
            return int(form.id)


def find_forms_by_hash(file_hash: str) -> list[dict[str, Any]]:
    if not file_hash:
        raise ValueError("file_hash is required.")

    with SessionLocal() as session:
        rows = session.execute(select(Form).where(Form.file_hash == file_hash).order_by(Form.id.asc())).scalars().all()
        return [
            {
                "id": form.id,
                "source_file": form.source_file,
                "file_hash": form.file_hash,
                "page_number": form.page_number,
                "image_path": form.image_path,
                "form_type": form.form_type,
                "status": form.status,
                "raw_llm_json": form.raw_llm_json,
                "error": form.error,
                "uploaded_at": form.uploaded_at,
            }
            for form in rows
        ]


def get_form(form_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        form = session.get(Form, form_id)
        if form is None:
            return None

        fields = session.execute(
            select(ExtractedField).where(ExtractedField.form_id == form_id).order_by(ExtractedField.id.asc())
        ).scalars().all()

        return {
            "id": form.id,
            "source_file": form.source_file,
            "file_hash": form.file_hash,
            "page_number": form.page_number,
            "image_path": form.image_path,
            "form_type": form.form_type,
            "status": form.status,
            "raw_llm_json": form.raw_llm_json,
            "error": form.error,
            "uploaded_at": form.uploaded_at,
            "fields": [
                {
                    "id": row.id,
                    "form_id": row.form_id,
                    "field_name": row.field_name,
                    "value": row.value,
                    "raw_value": row.raw_value,
                    "ocr_value": row.ocr_value,
                    "llm_value": row.llm_value,
                    "status": row.status,
                    "corrected_value": row.corrected_value,
                    "reason": row.reason,
                    "bbox": row.bbox,
                    "page": row.page,
                    "x": row.x,
                    "y": row.y,
                    "width": row.width,
                    "height": row.height,
                    "created_at": row.created_at,
                }
                for row in fields
            ],
        }


def claim_next_form() -> dict[str, Any] | None:
    for _ in range(10):
        with SessionLocal() as session:
            with session.begin():
                candidate = session.execute(
                    select(Form).where(Form.status == "uploaded").order_by(Form.id.asc()).limit(1)
                ).scalar_one_or_none()
                if candidate is None:
                    return None

                updated = session.execute(
                    update(Form)
                    .where(Form.id == candidate.id, Form.status == "uploaded")
                    .values(status="processing")
                )
                if updated.rowcount != 1:
                    continue

                session.flush()
                return {
                    "id": candidate.id,
                    "source_file": candidate.source_file,
                    "file_hash": candidate.file_hash,
                    "page_number": candidate.page_number,
                    "image_path": candidate.image_path,
                    "form_type": candidate.form_type,
                    "status": "processing",
                    "raw_llm_json": candidate.raw_llm_json,
                    "error": candidate.error,
                    "uploaded_at": candidate.uploaded_at,
                }
    return None


def set_form_status(form_id: int, status: str, error: str | None = None) -> None:
    _validate_status(status, FORM_STATUSES, "status")
    with SessionLocal() as session:
        with session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise ValueError(f"Form {form_id} not found.")
            form.status = status
            form.error = None if error is None else error


def _normalize_field_payload(entry: dict[str, Any]) -> dict[str, Any]:
    field_name = _validate_field_name(entry.get("field_name"))
    status_value = entry.get("status", "unverified")
    if status_value is not None:
        _validate_status(status_value, FIELD_STATUSES, "field status")

    raw_value = entry.get("raw_value")
    if raw_value is None:
        raw_value = entry.get("value")

    ocr_value = entry.get("ocr_value")
    if ocr_value is None:
        ocr_value = raw_value

    llm_value = entry.get("llm_value")
    if llm_value is None:
        llm_value = entry.get("value")

    if entry.get("value") is None and raw_value is None and ocr_value is None and llm_value is None:
        return {}

    bbox = entry.get("bbox")
    page = entry.get("page")
    reason = entry.get("reason")

    x = entry.get("x")
    y = entry.get("y")
    width = entry.get("width")
    height = entry.get("height")

    if bbox is None and any(value is not None for value in (x, y, width, height)):
        bbox = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

    if status_value in {None, ""}:
        status_value = "unverified"

    if str(ocr_value) != str(llm_value) and status_value == "unverified":
        status_value = "uncertain"
    if str(ocr_value) != str(llm_value) and reason in (None, ""):
        reason = "ברקוד פגום חלקית – קריאה חלקית בלבד"

    return {
        "field_name": field_name,
        "value": entry.get("value"),
        "raw_value": raw_value,
        "ocr_value": ocr_value,
        "llm_value": llm_value,
        "status": status_value or "unverified",
        "corrected_value": entry.get("corrected_value"),
        "reason": reason,
        "bbox": bbox,
        "page": page,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def save_extraction(form_id: int, raw_llm_json: str | None, form_type: str | None, fields: list[dict[str, Any]]) -> None:
    _validate_form_type(form_type)
    if form_id is None:
        raise ValueError("form_id is required.")

    with SessionLocal() as session:
        with session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise ValueError(f"Form {form_id} not found.")

            form.raw_llm_json = raw_llm_json
            form.form_type = form_type

            existing_fields = session.execute(
                select(ExtractedField).where(ExtractedField.form_id == form_id).order_by(ExtractedField.id.asc())
            ).scalars().all()
            preserved_manual_names = {field.field_name for field in existing_fields if field.corrected_value is not None}

            for field in existing_fields:
                if field.corrected_value is not None:
                    continue
                session.delete(field)

            normalized_fields: list[dict[str, Any]] = []
            for entry in fields or []:
                if not isinstance(entry, dict):
                    raise ValueError("Each field entry must be a dictionary.")

                if entry.get("field_name") == "sender":
                    raw_value = entry.get("raw_value")
                    if raw_value is None:
                        raw_value = entry.get("value")
                    if raw_value is None:
                        continue

                    sender_match = session.execute(select(Sender).where(Sender.name == raw_value)).scalar_one_or_none()
                    normalized = _normalize_field_payload(entry)
                    if not normalized:
                        continue
                    normalized["value"] = sender_match.name if sender_match is not None else None
                    normalized["raw_value"] = raw_value
                    normalized["status"] = normalized.get("status") or "uncertain"
                    if sender_match is None:
                        normalized["status"] = "uncertain"
                        normalized["reason"] = normalized.get("reason") or "שם השולח לא זוהה ב-DB"
                    normalized_fields.append(normalized)
                    continue

                normalized = _normalize_field_payload(entry)
                if normalized:
                    normalized_fields.append(normalized)

            for normalized in normalized_fields:
                field_name = normalized["field_name"]
                if field_name in preserved_manual_names:
                    continue
                session.add(
                    ExtractedField(
                        form_id=form_id,
                        field_name=field_name,
                        value=normalized.get("value"),
                        raw_value=normalized.get("raw_value"),
                        ocr_value=normalized.get("ocr_value"),
                        llm_value=normalized.get("llm_value"),
                        status=normalized.get("status", "unverified"),
                        corrected_value=normalized.get("corrected_value"),
                        reason=normalized.get("reason"),
                        bbox=normalized.get("bbox"),
                        page=normalized.get("page"),
                        x=normalized.get("x"),
                        y=normalized.get("y"),
                        width=normalized.get("width"),
                        height=normalized.get("height"),
                    )
                )

            form.status = "extracted"
            form.error = None
            session.flush()


def get_fields(form_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(ExtractedField).where(ExtractedField.form_id == form_id).order_by(ExtractedField.id.asc())
        ).scalars().all()
        return [
            {
                "id": row.id,
                "form_id": row.form_id,
                "field_name": row.field_name,
                "value": row.value,
                "raw_value": row.raw_value,
                "ocr_value": row.ocr_value,
                "llm_value": row.llm_value,
                "status": row.status,
                "corrected_value": row.corrected_value,
                "reason": row.reason,
                "bbox": row.bbox,
                "page": row.page,
                "x": row.x,
                "y": row.y,
                "width": row.width,
                "height": row.height,
                "created_at": row.created_at,
            }
            for row in rows
        ]


def _recalculate_form_status(session, form_id: int) -> None:
    form = session.get(Form, form_id)
    if form is None:
        return

    fields = session.execute(
        select(ExtractedField).where(ExtractedField.form_id == form_id).order_by(ExtractedField.id.asc())
    ).scalars().all()

    if not fields:
        form.status = "extracted"
        return

    if all(field.status == "confirmed" for field in fields):
        form.status = "approved"
    else:
        form.status = "extracted"


def update_field(field_id: int, status: str | None = None, corrected_value: Any = _UNSET) -> None:
    with SessionLocal() as session:
        with session.begin():
            field = session.get(ExtractedField, field_id)
            if field is None:
                raise ValueError(f"Field {field_id} not found.")
            if status is not None:
                _validate_status(status, FIELD_STATUSES, "field status")
                field.status = status
            if corrected_value is not _UNSET:
                field.corrected_value = corrected_value
            _recalculate_form_status(session, field.form_id)


def confirm_field(form_id: int, field_name: str, corrected_value: str | None, status: str = "confirmed") -> dict[str, Any]:
    _validate_status(status, FIELD_STATUSES, "field status")
    _validate_field_name(field_name)

    with SessionLocal() as session:
        with session.begin():
            field = session.execute(
                select(ExtractedField).where(ExtractedField.form_id == form_id, ExtractedField.field_name == field_name)
            ).scalar_one_or_none()
            if field is None:
                raise ValueError(f"Field {field_name!r} not found for form {form_id}.")

            field.status = status
            field.corrected_value = corrected_value
            field.value = corrected_value if corrected_value is not None else (field.value or field.ocr_value or field.llm_value)
            _recalculate_form_status(session, form_id)

            return {
                "id": field.id,
                "form_id": field.form_id,
                "field_name": field.field_name,
                "status": field.status,
                "corrected_value": field.corrected_value,
                "value": field.value,
                "raw_value": field.raw_value,
                "ocr_value": field.ocr_value,
                "llm_value": field.llm_value,
                "reason": field.reason,
            }


def list_forms_with_fields(status: str | None = "extracted", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if limit < 0 or offset < 0:
        raise ValueError("limit and offset must be non-negative.")
    if limit == 0:
        raise ValueError("limit must be greater than zero.")
    if limit > 500:
        raise ValueError("limit cannot exceed 500.")
    if status is not None:
        _validate_status(status, FORM_STATUSES, "form status")

    with SessionLocal() as session:
        query = select(Form).order_by(Form.id.asc()).limit(limit).offset(offset)
        if status is not None:
            query = query.where(Form.status == status)
        form_rows = session.execute(query).scalars().all()
        if not form_rows:
            return []

        form_ids = [form.id for form in form_rows]
        field_rows = session.execute(
            select(ExtractedField)
            .where(ExtractedField.form_id.in_(form_ids))
            .order_by(ExtractedField.form_id.asc(), ExtractedField.id.asc())
        ).scalars().all()

        by_form: dict[int, list[dict[str, Any]]] = {}
        for field in field_rows:
            by_form.setdefault(field.form_id, []).append(
                {
                    "id": field.id,
                    "form_id": field.form_id,
                    "field_name": field.field_name,
                    "value": field.value,
                    "raw_value": field.raw_value,
                    "ocr_value": field.ocr_value,
                    "llm_value": field.llm_value,
                    "status": field.status,
                    "corrected_value": field.corrected_value,
                    "reason": field.reason,
                    "bbox": field.bbox,
                    "page": field.page,
                    "x": field.x,
                    "y": field.y,
                    "width": field.width,
                    "height": field.height,
                    "created_at": field.created_at,
                }
            )

        result: list[dict[str, Any]] = []
        for form in form_rows:
            result.append(
                {
                    "id": form.id,
                    "source_file": form.source_file,
                    "file_hash": form.file_hash,
                    "page_number": form.page_number,
                    "image_path": form.image_path,
                    "form_type": form.form_type,
                    "status": form.status,
                    "raw_llm_json": form.raw_llm_json,
                    "error": form.error,
                    "uploaded_at": form.uploaded_at,
                    "fields": by_form.get(form.id, []),
                }
            )
        return result


def list_senders() -> list[tuple[str, str]]:
    with SessionLocal() as session:
        rows = session.execute(select(Sender).order_by(Sender.name.asc())).scalars().all()
        return [(row.name, row.kind) for row in rows]


def add_sender(name: str, kind: str) -> int:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Sender name cannot be empty.")
    if kind not in SENDER_KINDS:
        raise ValueError(f"Invalid sender kind: {kind!r}")

    with SessionLocal() as session:
        with session.begin():
            sender = Sender(name=normalized_name, kind=kind)
            session.add(sender)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError(f"Sender {normalized_name!r} already exists.") from exc
            return int(sender.id)


def select_rows(table: str, filters: dict[str, Any] | None = None, order_by: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if limit < 0:
        raise ValueError("limit must be non-negative.")
    if offset < 0:
        raise ValueError("offset must be non-negative.")
    if limit == 0:
        raise ValueError("limit must be greater than zero.")
    if limit > 500:
        raise ValueError("limit cannot exceed 500.")

    model_map = {"forms": Form, "extracted_fields": ExtractedField, "senders": Sender}
    model = model_map.get(table)
    if model is None:
        raise ValueError(f"Unknown table: {table!r}")

    query = select(model)
    for column_name, value in (filters or {}).items():
        if not hasattr(model, column_name):
            raise ValueError(f"Unknown column: {column_name!r}")
        column = getattr(model, column_name)
        if value is None:
            query = query.where(column.is_(None))
        else:
            query = query.where(column == value)

    if order_by:
        if order_by.startswith("-"):
            column_name = order_by[1:]
            direction = desc
        else:
            column_name = order_by
            direction = asc
        if not hasattr(model, column_name):
            raise ValueError(f"Unknown order_by column: {column_name!r}")
        query = query.order_by(direction(getattr(model, column_name)))

    query = query.limit(limit).offset(offset)

    with SessionLocal() as session:
        rows = session.execute(query).scalars().all()
        return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]


def delete_forms_by_hash(file_hash: str) -> int:
    if not file_hash:
        raise ValueError("file_hash is required.")

    with SessionLocal() as session:
        with session.begin():
            deleted = session.execute(delete(Form).where(Form.file_hash == file_hash)).rowcount
            return int(deleted or 0)


__all__ = [
    "add_form",
    "find_forms_by_hash",
    "get_form",
    "claim_next_form",
    "set_form_status",
    "save_extraction",
    "get_fields",
    "update_field",
    "list_forms_with_fields",
    "list_senders",
    "add_sender",
    "select_rows",
    "delete_forms_by_hash",
]
