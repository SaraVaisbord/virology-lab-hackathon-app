"""The lab worker's actions on a form's fields (confirm / correct / add / delete), each saved together with its
correction-history event (FieldEvent) in one transaction."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from db.models import ExtractedField, FieldEvent, Form
from db.serialization import (
    empty_field,
    form_to_dict,
    from_json,
    mark_rejected,
    recalculate_form_status,
    require_in,
    to_json,
    value_origin,
)
from domain.review_rules import display_value, manual_value, source_values
from domain.validators import classify_change, match_key
from domain.vocabulary import FIELDS, INVENTORY_KINDS, MULTI_VALUE_FIELDS, SOURCE_LABELS


def _written_as(form: Form, field_name: str, row: ExtractedField | None) -> str | None:
    """How the shown value is written on the page (an INVENTORY_KINDS key), as the AI listed it in all_numbers."""
    value = display_value(row) if row is not None else None
    if not value:
        return None
    key = match_key(field_name, value)
    numbers = (from_json(form.llm_result) or {}).get("all_numbers") or []
    return next((item["kind"] for item in numbers if isinstance(item, dict) and item.get("kind") in INVENTORY_KINDS
                 and match_key(field_name, item.get("value")) == key), None)


def _previous_event_id(session: Session, form: Form, before: ExtractedField | None) -> int | None:
    """The last event of the value this action continues: the row's own history, or — for the placeholder left by
    deleting a value — that deletion (its row is gone, so it can't be found by field_id)."""
    if before is None:
        return None
    last = select(FieldEvent.id).order_by(FieldEvent.id.desc()).limit(1)
    if before.id is not None:
        found = session.execute(last.where(FieldEvent.field_id == before.id)).scalar()
        if found is not None:
            return found
    if value_origin(before) == "manual" and before.status == "not_found":
        where = (FieldEvent.form_id == form.id, FieldEvent.field_name == before.field_name, FieldEvent.action == "delete")
        return session.execute(last.where(*where)).scalar()
    return None


def _lock_form(session: Session, form_id: int) -> Form | None:
    """The form with its fields, its row locked until the transaction ends: the worker's edits of one form run one at
    a time, so two concurrent requests (a double click) can't both record the same correction. On PostgreSQL this is
    SELECT … FOR UPDATE; SQLite has no row locks (and serializes writes anyway), so there it is a plain read."""
    return session.get(Form, form_id, options=[selectinload(Form.extracted_fields)], with_for_update=True)


def _correction_event(session: Session, form: Form, field_name: str, action: str, before: ExtractedField | None,
                      after: str | None, picked_from: str | None = None) -> FieldEvent | None:
    """The history event of one action, built from the field's state just before it — call it before changing
    anything. None when nothing new happened: a value the worker had already decided on, set again unchanged.
    The caller adds it in the same transaction as the change, so a change is never saved without its event.
    No value goes into the event, only what kind of change it was (see classify_change)."""
    origin = value_origin(before)
    other_fields: dict[str, list] = {}
    for row in form.extracted_fields:
        if row.field_name != field_name:
            other_fields.setdefault(row.field_name, []).extend([display_value(row), *source_values(row).values()])
    change = classify_change(
        field_name,
        display_value(before) if before is not None else None,
        after,
        other_fields=other_fields,
        machine_values=list(source_values(before).values()) if origin == "manual" else [],  # undoing her own change
    )
    if origin != "machine" and change["change_kind"] == "none":
        return None
    if action == "edit" and change["change_kind"] == "none":
        action = "confirm"  # "corrected" to the value it already showed
    seen = set()
    if change["change_kind"] not in ("none", "removed"):
        key = match_key(field_name, after)
        seen = {source for row in form.extracted_fields for source, value in source_values(row).items()
                if match_key(field_name, value) == key}
        seen.update([picked_from] if picked_from else [])
    evidence = (from_json(before.evidence) or {}) if before is not None else {}
    return FieldEvent(
        form_id=form.id,
        field_id=before.id if before is not None else None,
        previous_event_id=_previous_event_id(session, form, before),
        field_name=field_name,
        action=action,
        **change,
        before_origin=origin,
        before_written_as=_written_as(form, field_name, before),
        before_status=before.status if before is not None else None,
        before_confidence=before.confidence if before is not None else None,
        before_sources=",".join(sorted(evidence.get("sources") or [])) or None,
        correct_seen_by=",".join(sorted(seen)) or None,
    )


def _event_to_dict(row: FieldEvent) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in FieldEvent.__table__.columns}


class ReviewRepository:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def add_manual_field(
        self,
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
        require_in(field_name, FIELDS, "field_name")
        value = (value or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        value = manual_value(field_name, value)
        if picked_from is not None:
            require_in(picked_from, SOURCE_LABELS, "source")
        with self._sessions() as session, session.begin():
            form = _lock_form(session, form_id)
            if form is None:
                raise LookupError(f"Form {form_id} not found.")
            existing = [row for row in form.extracted_fields if row.field_name == field_name]
            has_value = any(row.status != "not_found" for row in existing)
            if field_name not in MULTI_VALUE_FIELDS and has_value and not replace:
                raise ValueError(f"{field_name} already has a value — edit it instead.")
            replaced = [row for row in existing if row.status != "not_found" and replace and field_name not in MULTI_VALUE_FIELDS]
            placeholder = next((row for row in existing if row.status == "not_found"), None)
            event = _correction_event(session, form, field_name, "replace" if replaced else "add",
                                      replaced[0] if replaced else placeholder, value, picked_from=picked_from)
            for row in existing:
                # The "not found" placeholder always goes; a single-value field's old value goes when replaced.
                if row.status == "not_found" or (replace and field_name not in MULTI_VALUE_FIELDS):
                    form.extracted_fields.remove(row)
            coordinates = {key: float(box[key]) for key in ("x", "y", "width", "height")} if box else {}
            mark_rejected(form, field_name, value, is_rejected_now=False)  # set again on purpose: no longer rejected
            added = ExtractedField(
                field_name=field_name, value=value, corrected_value=value, status="confirmed",
                evidence=to_json({"manual": True, **({"picked_from": picked_from} if picked_from else {})}),
                box_source=picked_from if box else None,
                **coordinates,
            )
            form.extracted_fields.append(added)
            session.flush()
            if event is not None:
                event.field_id = added.id  # the field as it is now — the row it replaced is gone
                session.add(event)
                session.flush()
            recalculate_form_status(form, keep_pending=True)
            return form_to_dict(form, with_sources=True)

    def delete_field(self, form_id: int, field_id: int) -> dict[str, Any]:
        """Remove a value the lab worker rejected. It is remembered as rejected, so re-extraction never puts it back;
        a field left with no value gets a 'not found' row — it still needs her decision (fill it or confirm it empty)."""
        with self._sessions() as session, session.begin():
            form = _lock_form(session, form_id)
            row = next((r for r in form.extracted_fields if r.id == field_id), None) if form else None
            if row is None:
                raise LookupError(f"Field {field_id} not found for form {form_id}.")
            value = display_value(row)
            event = None
            if value:
                event = _correction_event(session, form, row.field_name, "delete", row, None)
                mark_rejected(form, row.field_name, value, is_rejected_now=True)
                event.field_id = None  # the row is deleted in this transaction
            form.extracted_fields.remove(row)
            if not any(other.field_name == row.field_name for other in form.extracted_fields):
                form.extracted_fields.append(empty_field(form, row.field_name))
            if event is not None:
                session.add(event)
            session.flush()
            recalculate_form_status(form, keep_pending=True)
            return form_to_dict(form, with_sources=True)

    def confirm_field(self, form_id: int, field_id: int, corrected_value: str | None) -> dict[str, Any]:
        """Human approval of one field value (optionally corrected)."""
        with self._sessions() as session, session.begin():
            form = _lock_form(session, form_id)
            row = next((r for r in form.extracted_fields if r.id == field_id), None) if form else None
            if row is None:
                raise LookupError(f"Field {field_id} not found for form {form_id}.")

            if corrected_value is not None:
                corrected_value = manual_value(row.field_name, corrected_value.strip())
            changed = corrected_value is not None and corrected_value != row.value
            event = _correction_event(session, form, row.field_name, "edit" if changed else "confirm", row,
                                      corrected_value if changed else display_value(row))
            if changed:
                row.corrected_value = corrected_value
                row.value = corrected_value
            if row.value:
                mark_rejected(form, row.field_name, row.value, is_rejected_now=False)
            row.status = "confirmed"
            if event is not None:
                session.add(event)
            session.flush()

            recalculate_form_status(form, keep_pending=True)
            return form_to_dict(form, with_sources=True)

    def list_field_events(self, form_id: int) -> list[dict[str, Any]]:
        """The correction history of one form, oldest first."""
        with self._sessions() as session:
            rows = session.execute(select(FieldEvent).where(FieldEvent.form_id == form_id).order_by(FieldEvent.id)).scalars()
            return [_event_to_dict(row) for row in rows]

