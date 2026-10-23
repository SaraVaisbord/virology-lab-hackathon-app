"""Forms (one per uploaded page): create / read / delete, the extraction queue, and the extraction results."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload, sessionmaker

from db.models import ExtractedField, Form
from db.serialization import (
    SOURCE_COLUMNS,
    empty_field,
    form_to_dict,
    recalculate_form_status,
    rejected,
    require_in,
    to_json,
)
from domain import review_rules
from domain.vocabulary import FIELD_STATUSES, FIELDS, FORM_STATUSES, FORM_TYPES, PENDING_FORM_STATUSES

# Columns of a field row that extraction may write (the rest belong to the database or to the lab worker).
_WRITABLE_FIELD_KEYS = {
    "value", "llm_value", "barcode_value", "ocr_value", "status", "confidence", "reason",
    "box_source", "page", "x", "y", "width", "height",
}


class FormRepository:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    # ── Forms ────────────────────────────────────────────────────────────────

    def add_form(self, source_file: str, file_hash: str, page_number: int, image_path: str) -> int:
        if not source_file or not file_hash or not image_path:
            raise ValueError("source_file, file_hash and image_path are required.")
        if not isinstance(page_number, int):
            raise ValueError("page_number must be an integer.")

        with self._sessions() as session, session.begin():
            form = Form(source_file=source_file, file_hash=file_hash, page_number=page_number, image_path=image_path, status="uploaded")
            session.add(form)
            session.flush()
            return int(form.id)

    def find_forms_by_hash(self, file_hash: str) -> list[dict[str, Any]]:
        if not file_hash:
            raise ValueError("file_hash is required.")
        with self._sessions() as session:
            rows = session.execute(select(Form).where(Form.file_hash == file_hash).order_by(Form.id)).scalars().all()
            return [form_to_dict(form, with_fields=False) for form in rows]

    def get_form(self, form_id: int, *, with_sources: bool = False) -> dict[str, Any] | None:
        with self._sessions() as session:
            form = session.get(Form, form_id, options=[selectinload(Form.extracted_fields)])
            return form_to_dict(form, with_sources=with_sources) if form is not None else None

    def delete_forms_by_hash(self, file_hash: str) -> int:
        if not file_hash:
            raise ValueError("file_hash is required.")
        with self._sessions() as session, session.begin():
            return int(session.execute(delete(Form).where(Form.file_hash == file_hash)).rowcount or 0)

    def delete_form(self, form_id: int) -> dict[str, Any]:
        """Delete one form (page) and its fields. Refused while it is being processed (the worker holds it).
        Returns what the caller must clean up in file storage: the page image and, when no other page of the same
        upload is left, the uploaded file itself."""
        with self._sessions() as session, session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise LookupError(f"Form {form_id} not found.")
            if form.status == "processing":
                raise ValueError("הטופס בעיבוד כרגע – אפשר למחוק אותו אחרי שהעיבוד יסתיים")
            image_path, file_hash = form.image_path, form.file_hash
            session.delete(form)  # fields go with it (cascade)
            session.flush()
            others = session.execute(select(func.count(Form.id)).where(Form.file_hash == file_hash)).scalar_one()
            return {"image_path": image_path, "file_hash": file_hash, "last_page_of_upload": others == 0}

    def set_form_status(self, form_id: int, status: str, error: str | None = None) -> None:
        require_in(status, FORM_STATUSES, "form status")
        with self._sessions() as session, session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise ValueError(f"Form {form_id} not found.")
            form.status = status
            form.error = error

    # ── Extraction queue ─────────────────────────────────────────────────────

    def claim_next_form(self) -> dict[str, Any] | None:
        """Atomically move the oldest queued form to 'processing' and return it (None when the queue is empty)."""
        for _ in range(10):
            with self._sessions() as session, session.begin():
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

    def requeue_stale_processing(self) -> int:
        """Forms left in 'processing' by a crashed/stopped server go back to the queue."""
        with self._sessions() as session, session.begin():
            return int(session.execute(update(Form).where(Form.status == "processing").values(status="uploaded")).rowcount or 0)

    def return_to_queue(self, form_id: int) -> None:
        """Put a claimed form back in the queue (e.g. the model was rate-limited, not the form's fault)."""
        with self._sessions() as session, session.begin():
            session.execute(update(Form).where(Form.id == form_id, Form.status == "processing").values(status="uploaded"))

    def requeue_form(self, form_id: int) -> None:
        with self._sessions() as session, session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise ValueError(f"Form {form_id} not found.")
            if form.status in PENDING_FORM_STATUSES:
                return
            form.status = "uploaded"
            form.error = None

    # ── Extraction results ───────────────────────────────────────────────────

    def save_source_results(self, form_id: int, **results: Any) -> None:
        """Persist raw results of individual sources (llm_result / barcode_result / ocr_result / source_errors).

        Called per source as soon as it finishes, so a later failure of another source can't discard them.
        """
        unknown = set(results) - set(SOURCE_COLUMNS)
        if unknown:
            raise ValueError(f"Unknown source columns: {sorted(unknown)}")
        with self._sessions() as session, session.begin():
            form = session.get(Form, form_id)
            if form is None:
                raise ValueError(f"Form {form_id} not found.")
            for column, value in results.items():
                setattr(form, column, to_json(value))

    def save_extraction(self, form_id: int, fields: list[dict[str, Any]], form_type: str | None = None) -> None:
        """Replace the machine-extracted fields of a form. Fields a human already decided on (confirmed or
        corrected) are kept as-is, and values the lab worker deleted are never put back — so re-extraction /
        re-verification never discards a human decision.

        Raw source results are stored separately via save_source_results().
        """
        if form_type is not None:
            require_in(form_type, FORM_TYPES, "form_type")

        with self._sessions() as session, session.begin():
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
                name = require_in(entry.get("field_name"), FIELDS, "field_name")
                if name in human_corrected or review_rules.is_rejected(rejected(form), name, entry.get("value") or entry.get("llm_value")):
                    continue
                require_in(entry.get("status", "unverified"), FIELD_STATUSES, "field status")
                form.extracted_fields.append(
                    ExtractedField(
                        field_name=name,
                        evidence=to_json(entry.get("evidence")),
                        **{key: entry[key] for key in _WRITABLE_FIELD_KEYS if key in entry},
                    )
                )
            # A field whose every reading was rejected still needs a decision.
            present = {row.field_name for row in form.extracted_fields}
            for name in FIELDS:
                if name not in present and rejected(form).get(name):
                    form.extracted_fields.append(empty_field(form, name))

            form.form_type = form_type
            form.error = None
            session.flush()
            recalculate_form_status(form)
