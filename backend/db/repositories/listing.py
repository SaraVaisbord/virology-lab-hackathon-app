"""The forms table: paging, filtering and sorting (all in SQL), and the processing summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, String, and_, asc, cast, desc, exists, func, or_, select
from sqlalchemy.orm import selectinload, sessionmaker

from db.models import ExtractedField, Form
from db.serialization import commitment_duplicates, field_display_value, form_to_dict, require_in
from domain.vocabulary import FIELDS, FORM_COLUMN_LABELS, FORM_STATUSES, PENDING_FORM_STATUSES, REVIEW_FIELD_STATUSES

FORM_SORT_COLUMNS = {name: getattr(Form, name) for name in FORM_COLUMN_LABELS}


@dataclass
class FormFilters:
    status: str | None = None
    query: str | None = None
    column_filters: dict[str, str] = field(default_factory=dict)
    sort_by: str = "id"
    sort_dir: str = "desc"


def _field_matches(field_name: str | None, needle: str):
    conditions = [ExtractedField.form_id == Form.id, field_display_value().ilike(f"%{needle}%")]
    if field_name is not None:
        conditions.append(ExtractedField.field_name == field_name)
    return exists().where(and_(*conditions))


def _apply_filters(stmt: Select, filters: FormFilters) -> Select:
    if filters.status:
        stmt = stmt.where(Form.status == require_in(filters.status, FORM_STATUSES, "form status"))

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
            select(func.min(field_display_value()))
            .where(ExtractedField.form_id == Form.id, ExtractedField.field_name == filters.sort_by)
            .scalar_subquery()
        )
        # Forms without this field always last — PostgreSQL would otherwise put them first in descending order.
        return direction(first_value).nulls_last()
    raise ValueError(f"Unknown sort column: {filters.sort_by!r}")


class FormListing:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def list_forms(self, filters: FormFilters, limit: int, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Return one page of forms (with fields) and the total number of matching forms."""
        if limit <= 0 or offset < 0:
            raise ValueError("limit must be positive and offset non-negative.")

        with self._sessions() as session:
            total = session.execute(_apply_filters(select(func.count(Form.id)), filters)).scalar_one()
            stmt = (
                _apply_filters(select(Form), filters)
                .options(selectinload(Form.extracted_fields))
                .order_by(_sort_expression(filters), desc(Form.id))
                .limit(limit)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            duplicates = commitment_duplicates(session, [form.id for form in rows])
            return [form_to_dict(form, duplicates=duplicates[form.id]) for form in rows], int(total)

    def forms_summary(self) -> dict[str, Any]:
        with self._sessions() as session:
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
