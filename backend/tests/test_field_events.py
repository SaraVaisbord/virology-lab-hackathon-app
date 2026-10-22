"""Correction history (field_events): one appended event per action of the lab worker, holding no field values."""

from __future__ import annotations

import itertools
import os
import threading

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from tests.conftest import alembic_config, make_form
from validators import classify_change

# A commitment number the AI misread by one digit, while the barcode read it right.
_MISREAD = {
    "field_name": "commitment_number", "value": "47321", "llm_value": "47321", "barcode_value": "47381",
    "status": "conflict", "confidence": "medium", "evidence": {"sources": ["barcode", "llm"]},
}
_ID = {"field_name": "id_number", "value": "000000018", "llm_value": "000000018", "status": "unverified",
       "confidence": "high", "evidence": {"sources": ["llm"]}}
_DATE = {"field_name": "received_date", "value": "01/02/2024", "llm_value": "1.2.24", "status": "uncertain",
         "confidence": "low", "evidence": {"sources": ["llm"]}}
_BOX = {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}
_HASHES = itertools.count()


def _form_with(queries, *fields, llm_result=None) -> tuple[int, dict[str, int]]:
    form_id = make_form(queries, file_hash=f"hash-{next(_HASHES)}")
    if llm_result is not None:
        queries.save_source_results(form_id, llm_result=llm_result)
    queries.save_extraction(form_id, [dict(field) for field in fields])
    return form_id, {row["field_name"]: row["id"] for row in queries.get_form(form_id)["fields"]}


def _field(queries, form_id: int, field_id: int) -> dict:
    return next(row for row in queries.get_form(form_id)["fields"] if row["id"] == field_id)


def _summary(events, *keys) -> list[tuple]:
    return [tuple(event[key] for key in keys) for event in events]


# ── Classification (pure) ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field_name", "before", "after", "kwargs", "expected"),
    [
        ("commitment_number", "47321", "47321", {}, {"change_kind": "none"}),
        ("id_number", "000000018", "000-000-018", {}, {"change_kind": "format_only"}),
        ("received_date", "1.2.2024", "01/02/2024", {}, {"change_kind": "format_only"}),
        ("commitment_number", "47321", "47381", {}, {"change_kind": "typo", "chars_changed": 1, "digit_swaps": "2>8"}),
        ("id_number", "000000018", "000000076", {}, {"change_kind": "typo", "chars_changed": 2, "digit_swaps": "1>7,8>6"}),
        ("first_name", "דנה", "דינה", {}, {"change_kind": "typo", "chars_changed": 1, "digit_swaps": None}),
        ("commitment_number", "47321", "47312", {}, {"change_kind": "transposition"}),
        ("received_date", "03/02/2024", "02/03/2024", {}, {"change_kind": "day_month_swap"}),
        ("commitment_number", "47321", "99999", {}, {"change_kind": "different_value"}),
        ("commitment_number", "47321", "904412", {"other_fields": {"central_number": ["904-412"]}},
         {"change_kind": "wrong_field", "matched_field": "central_number"}),
        ("commitment_number", None, "47321", {}, {"change_kind": "filled_missing"}),
        ("commitment_number", "47321", None, {}, {"change_kind": "removed", "matched_field": None}),
        ("commitment_number", "904412", None, {"other_fields": {"central_number": ["904412"]}},
         {"change_kind": "removed", "matched_field": "central_number"}),
        ("commitment_number", "47381", "47321", {"machine_values": ["47321"]}, {"change_kind": "restored"}),
    ],
)
def test_classify_change(field_name, before, after, kwargs, expected):
    result = classify_change(field_name, before, after, **kwargs)
    assert set(result) == {"change_kind", "chars_changed", "matched_field", "digit_swaps"}
    assert {key: result[key] for key in expected} == expected


# ── Recording, through the existing correction functions ────────────────────


def test_first_correction_records_one_event_and_keeps_current_behaviour(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD, llm_result={"all_numbers": [{"value": "47321", "kind": "handwritten"}]})
    form = queries.confirm_field(form_id, ids["commitment_number"], corrected_value="47381")

    field = next(row for row in form["fields"] if row["id"] == ids["commitment_number"])
    assert (field["value"], field["corrected_value"], field["status"]) == ("47381", "47381", "confirmed")
    assert form["status"] == "approved"
    [event] = queries.list_field_events(form_id)
    assert {key: event[key] for key in event if key not in ("id", "form_id", "created_at")} == {
        "field_id": ids["commitment_number"], "previous_event_id": None, "field_name": "commitment_number",
        "action": "edit", "change_kind": "typo", "chars_changed": 1, "matched_field": None, "digit_swaps": "2>8",
        "before_origin": "machine", "before_written_as": "handwritten", "before_status": "conflict",
        "before_confidence": "medium", "before_sources": "barcode,llm", "correct_seen_by": "barcode",
    }
    assert event["created_at"] is not None


def test_repeated_correction_appends_without_touching_earlier_events(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD)
    field_id = ids["commitment_number"]
    queries.confirm_field(form_id, field_id, corrected_value="47381")
    [first] = queries.list_field_events(form_id)

    queries.confirm_field(form_id, field_id, corrected_value="47389")  # changes her own value
    queries.confirm_field(form_id, field_id, corrected_value="47321")  # back to what the AI read: undoes the correction

    events = queries.list_field_events(form_id)
    assert events[0] == first
    assert _summary(events, "action", "change_kind", "before_origin", "before_status") == [
        ("edit", "typo", "machine", "conflict"),
        ("edit", "typo", "manual", "confirmed"),
        ("edit", "restored", "manual", "confirmed"),
    ]
    assert [e["previous_event_id"] for e in events] == [None, events[0]["id"], events[1]["id"]]
    assert all(e["field_id"] == field_id for e in events)
    assert _field(queries, form_id, field_id)["value"] == "47321"


def test_unchanged_value(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _ID)
    field_id = ids["id_number"]

    # Approving the machine's value as-is is recorded (it is what accuracy is measured against) — as no change.
    queries.confirm_field(form_id, field_id, corrected_value=None)
    queries.confirm_field(form_id, field_id, corrected_value="000000018")  # already decided, same value
    queries.confirm_field(form_id, field_id, corrected_value=None)
    events = queries.list_field_events(form_id)
    assert _summary(events, "action", "change_kind", "before_origin") == [("confirm", "none", "machine")]
    assert events[0]["correct_seen_by"] is None
    field = _field(queries, form_id, field_id)
    assert (field["value"], field["corrected_value"], field["status"]) == ("000000018", None, "confirmed")

    # A "correction" to the value the machine already showed is a confirmation too, not a correction.
    other_id, other_ids = _form_with(queries, _ID)
    queries.confirm_field(other_id, other_ids["id_number"], corrected_value=" 000000018 ")
    assert _summary(queries.list_field_events(other_id), "action", "change_kind") == [("confirm", "none")]


def test_approving_the_ai_value_and_correcting_it_later_are_told_apart(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD)
    queries.confirm_field(form_id, ids["commitment_number"], corrected_value=None)  # approves the AI's value
    queries.confirm_field(form_id, ids["commitment_number"], corrected_value="47381")  # then finds the mistake
    assert _summary(queries.list_field_events(form_id), "action", "change_kind", "before_origin") == [
        ("confirm", "none", "machine"),
        ("edit", "typo", "machine_confirmed"),
    ]


def test_history_stays_connected_across_replace_and_delete(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _DATE)
    queries.confirm_field(form_id, ids["received_date"], corrected_value=None)
    form = queries.add_manual_field(form_id, "received_date", "03/02/2024", replace=True, picked_from="ocr", box=_BOX)
    [current] = [row for row in form["fields"] if row["field_name"] == "received_date"]
    queries.delete_field(form_id, current["id"])
    queries.add_manual_field(form_id, "received_date", "04/02/2024")  # fills the field she emptied

    events = queries.list_field_events(form_id)
    assert _summary(events, "action", "change_kind", "before_origin") == [
        ("confirm", "none", "machine"),
        ("replace", "typo", "machine_confirmed"),
        ("delete", "removed", "manual"),
        ("add", "filled_missing", "manual"),
    ]
    assert [e["previous_event_id"] for e in events] == [None, *[e["id"] for e in events[:-1]]]
    # The rows the first events pointed at are gone; the chain above is what still connects them.
    assert [e["field_id"] for e in events[:3]] == [None, None, None]
    assert events[3]["field_id"] == _summary(queries.get_form(form_id)["fields"], "id")[0][0]


def test_wrong_field_replace_add_and_delete(app_env):
    from db import queries

    swapped = [
        {"field_name": "first_name", "value": "כהן", "llm_value": "כהן", "status": "verified"},
        {"field_name": "last_name", "value": "דנה", "llm_value": "דנה", "status": "verified"},
    ]
    form_id, ids = _form_with(queries, *swapped, _MISREAD)

    queries.confirm_field(form_id, ids["first_name"], corrected_value="דנה")
    form = queries.add_manual_field(form_id, "commitment_number", "47381", picked_from="barcode")  # multi-value: added
    form = queries.add_manual_field(form_id, "id_number", "000000018")  # was not found at all
    form = queries.delete_field(form_id, ids["last_name"])

    events = queries.list_field_events(form_id)
    assert _summary(events, "field_name", "action", "change_kind", "matched_field") == [
        ("first_name", "edit", "wrong_field", "last_name"),
        ("commitment_number", "add", "filled_missing", None),
        ("id_number", "add", "filled_missing", None),
        ("last_name", "delete", "removed", "first_name"),  # the same value is now under first_name
    ]
    added = {row["field_name"]: row["id"] for row in form["fields"] if row["corrected_value"]}
    assert events[1]["field_id"] == next(row["id"] for row in form["fields"] if row["value"] == "47381")
    assert events[1]["correct_seen_by"] == "barcode"
    assert events[2]["field_id"] == added["id_number"] and events[2]["before_status"] is None
    assert events[3]["field_id"] is None and events[3]["before_origin"] == "machine"


def test_replace_links_the_event_to_the_new_field(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _DATE)
    form = queries.add_manual_field(form_id, "received_date", "03/02/2024", replace=True, picked_from="ocr", box=_BOX)
    [new_row] = [row for row in form["fields"] if row["field_name"] == "received_date"]
    [event] = queries.list_field_events(form_id)
    assert new_row["id"] != ids["received_date"]
    assert _summary([event], "field_id", "action", "change_kind", "chars_changed", "digit_swaps") == [
        (new_row["id"], "replace", "typo", 1, "1>3")]
    assert (event["before_status"], event["before_confidence"], event["correct_seen_by"]) == ("uncertain", "low", "ocr")

    # Picking the same value again changes nothing — no event.
    queries.add_manual_field(form_id, "received_date", "03/02/2024", replace=True)
    assert len(queries.list_field_events(form_id)) == 1


def test_events_hold_no_field_values(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD, _ID, {"field_name": "first_name", "value": "ישראלה", "status": "verified"},
                              llm_result={"all_numbers": [{"value": "000000018", "kind": "printed"}]})
    queries.confirm_field(form_id, ids["commitment_number"], corrected_value="47381")
    queries.confirm_field(form_id, ids["id_number"], corrected_value="000000026")
    queries.delete_field(form_id, ids["first_name"])

    secrets = {"47321", "47381", "000000018", "000000026", "ישראלה"}
    events = queries.list_field_events(form_id)
    stored = [str(value) for event in events for value in event.values() if value is not None]
    assert len(events) == 3
    assert not [value for value in stored if any(secret in value for secret in secrets)]


@pytest.mark.parametrize("action", ["confirm", "add", "delete"])
def test_event_failure_rolls_back_the_correction(app_env, monkeypatch, action):
    """A correction is never saved without its event: if the event can't be stored, the field stays as it was."""
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD)
    before = queries.get_form(form_id)
    real = queries._correction_event

    def broken(*args, **kwargs):
        event = real(*args, **kwargs)
        event.action = "not-an-action"  # rejected by the table's check constraint at flush
        return event

    monkeypatch.setattr(queries, "_correction_event", broken)
    with pytest.raises(IntegrityError):
        if action == "confirm":
            queries.confirm_field(form_id, ids["commitment_number"], corrected_value="47381")
        elif action == "add":
            queries.add_manual_field(form_id, "id_number", "000000018")
        else:
            queries.delete_field(form_id, ids["commitment_number"])

    after = queries.get_form(form_id)
    assert after["fields"] == before["fields"]
    assert (after["status"], after["rejected_values"]) == (before["status"], before["rejected_values"])
    assert queries.list_field_events(form_id) == []


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="row locks exist on PostgreSQL only")
def test_concurrent_confirmations_record_one_event(app_env):
    """A double click sends two confirmations at once: the form's row lock lets only one of them record."""
    from db import queries

    form_id, ids = _form_with(queries, _ID)
    start, errors = threading.Barrier(6), []

    def confirm():
        start.wait()
        try:
            queries.confirm_field(form_id, ids["id_number"], corrected_value=None)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=confirm) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert _summary(queries.list_field_events(form_id), "action", "change_kind") == [("confirm", "none")]


def test_deleting_the_form_deletes_its_events(app_env):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD)
    queries.confirm_field(form_id, ids["commitment_number"], corrected_value="47381")
    queries.delete_form(form_id)
    assert queries.list_field_events(form_id) == []


def test_api_correction_records_event_and_response_is_unchanged(client):
    from db import queries

    form_id, ids = _form_with(queries, _MISREAD)
    response = client.patch(f"/forms/{form_id}/fields/{ids['commitment_number']}/confirm", json={"corrected_value": "47381"})
    assert response.status_code == 200
    assert "events" not in response.json() and "field_events" not in response.json()
    assert [e["change_kind"] for e in queries.list_field_events(form_id)] == ["typo"]


def test_every_allowed_value_fits_its_column():
    """SQLite ignores VARCHAR lengths, PostgreSQL enforces them — catch a value that is too long before it gets there."""
    from db.constants import CHANGE_KINDS, CONFIDENCE_LEVELS, FIELD_EVENT_ACTIONS, FIELD_STATUSES, FIELDS, INVENTORY_KINDS, SOURCE_LABELS, VALUE_ORIGINS
    from db.models import FieldEvent

    columns = FieldEvent.__table__.columns
    allowed = {
        "field_name": FIELDS, "matched_field": FIELDS, "action": FIELD_EVENT_ACTIONS, "change_kind": CHANGE_KINDS,
        "before_origin": VALUE_ORIGINS, "before_status": FIELD_STATUSES, "before_confidence": CONFIDENCE_LEVELS,
        "before_written_as": INVENTORY_KINDS,
        "before_sources": [",".join(sorted(SOURCE_LABELS))], "correct_seen_by": [",".join(sorted(SOURCE_LABELS))],
        "digit_swaps": [",".join(["0>9"] * 2)],  # a typo changes at most TYPO_MAX_CHANGED_CHARS (2) digits
    }
    too_long = {name: value for name, values in allowed.items() for value in values if len(value) > columns[name].type.length}
    assert too_long == {}


def test_migration_adds_and_removes_the_table(app_env):
    import db.session

    def tables():
        engine = create_engine(db.session.DATABASE_URL, future=True)
        try:
            return set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    assert "field_events" in tables()
    command.downgrade(alembic_config(), "d4e5f6a7b8c9")
    assert "field_events" not in tables() and {"forms", "extracted_fields"} <= tables()
    command.upgrade(alembic_config(), "head")
    assert "field_events" in tables()
