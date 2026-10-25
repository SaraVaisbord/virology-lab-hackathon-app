"""The correction history as read for pattern analysis (correction insights)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from db.models import ExtractedField, FieldEvent, Form
from db.serialization import field_display_value, require_in
from domain.vocabulary import FIELDS, SENDER_FIELD


class CorrectionHistory:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def correction_events(self, since: datetime | None = None, until: datetime | None = None,
                          field_name: str | None = None) -> list[dict[str, Any]]:
        """The correction history for pattern analysis, oldest first (one query): each event with its form's type and
        the form's sender as read (`sender_text` — free text: the caller matches it to the known senders and passes
        on only that name). No other field value is read.

        Plain columns and one sender lookup per form (a grouped join), not ORM objects and a per-row subquery:
        measured on 200,000 events that is 3 s instead of 9 s."""
        if field_name is not None:
            require_in(field_name, FIELDS, "field_name")
        sender_per_form = (
            select(ExtractedField.form_id, func.min(field_display_value()).label("sender_text"))
            .where(ExtractedField.field_name == SENDER_FIELD)
            .group_by(ExtractedField.form_id)
            .subquery()
        )
        stmt = (
            select(*FieldEvent.__table__.columns, Form.form_type, sender_per_form.c.sender_text)
            .join(Form, Form.id == FieldEvent.form_id)
            .outerjoin(sender_per_form, sender_per_form.c.form_id == FieldEvent.form_id)
            .order_by(FieldEvent.id)
        )
        if since is not None:
            stmt = stmt.where(FieldEvent.created_at >= since)
        if until is not None:
            stmt = stmt.where(FieldEvent.created_at <= until)
        if field_name is not None:
            stmt = stmt.where(FieldEvent.field_name == field_name)
        with self._sessions() as session:
            return [dict(row) for row in session.execute(stmt).mappings()]

    def count_unreviewed_verified_fields(self, since: datetime | None = None, until: datetime | None = None,
                                         field_name: str | None = None) -> int:
        """Fields the extraction marked verified that the lab worker never decided on (forms uploaded in the range):
        accepted without review, so they are not in the correction history."""
        if field_name is not None:
            require_in(field_name, FIELDS, "field_name")
        stmt = select(func.count(ExtractedField.id)).join(Form, Form.id == ExtractedField.form_id).where(
            ExtractedField.status == "verified"
        )
        if since is not None:
            stmt = stmt.where(Form.uploaded_at >= since)
        if until is not None:
            stmt = stmt.where(Form.uploaded_at <= until)
        if field_name is not None:
            stmt = stmt.where(ExtractedField.field_name == field_name)
        with self._sessions() as session:
            return int(session.execute(stmt).scalar_one())
