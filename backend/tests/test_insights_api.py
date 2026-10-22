"""GET /insights/corrections — patterns in the correction history, with no field values in the response."""

from __future__ import annotations

import itertools
from datetime import datetime

import pytest

from tests.conftest import make_form

_HASHES = itertools.count()
_SECRETS = ("47321", "47381", "000000018", "ישראלה", "שירותי בריאות")  # values on the dummy forms
_URL = "/insights/corrections"


def _reviewed_form(queries, *, verified=True, correct=True, form_type="clalit"):
    """A form whose commitment number the AI misread (2 read where 8 is written, handwritten) while the barcode read
    it right; the lab worker fixes it (or not) and approves the other three fields as they are."""
    form_id = make_form(queries, file_hash=f"h{next(_HASHES)}")
    queries.save_source_results(form_id, llm_result={"all_numbers": [{"value": "47321", "kind": "handwritten"}]})
    queries.save_extraction(form_id, [
        {"field_name": "commitment_number", "value": "47321", "llm_value": "47321", "barcode_value": "47381",
         "status": "verified" if verified else "conflict", "evidence": {"sources": ["llm"]}},
        {"field_name": "id_number", "value": "000000018", "llm_value": "000000018", "status": "unverified"},
        {"field_name": "first_name", "value": "ישראלה", "llm_value": "ישראלה", "status": "unverified"},
        {"field_name": "sender", "value": "שירותי בריאות כללית", "llm_value": "שירותי בריאות כללית", "status": "unverified"},
    ], form_type=form_type)
    for field in queries.get_form(form_id)["fields"]:
        fix = correct and field["field_name"] == "commitment_number"
        queries.confirm_field(form_id, field["id"], corrected_value="47381" if fix else None)
    return form_id


def _assert_no_values(response):
    assert not [secret for secret in _SECRETS if secret in response.text]


def test_no_history_yet(client):
    response = client.get(_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["message"] == "אין עדיין מספיק תיקונים לזיהוי דפוסים: נבדקו 0 ערכים, נדרשים לפחות 20"
    assert body["insights"] == []
    assert body["coverage"] == {"reviewed_fields": 0, "corrected_fields": 0, "required_reviewed_fields": 20,
                                "auto_accepted_fields": 0, "by_field": []}


def test_not_enough_corrections_yet(client):
    from db import queries

    for _ in range(2):
        _reviewed_form(queries)  # 4 reviewed values each: 8 < 20
    body = client.get(_URL).json()
    assert body["status"] == "insufficient_data" and body["insights"] == []
    assert (body["coverage"]["reviewed_fields"], body["coverage"]["corrected_fields"]) == (8, 2)
    assert "נבדקו 8 ערכים" in body["message"]


def test_insights_from_recurring_corrections(client):
    from db import queries

    queries.add_sender("כללית", "health_fund")
    for _ in range(8):
        _reviewed_form(queries)

    response = client.get(_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["message"] is None
    assert body["coverage"] == {
        "reviewed_fields": 32, "corrected_fields": 8, "required_reviewed_fields": 20, "auto_accepted_fields": 0,
        "by_field": [  # most corrected first
            {"field_name": "commitment_number", "reviewed": 8, "corrected": 8},
            {"field_name": "first_name", "reviewed": 8, "corrected": 0},
            {"field_name": "id_number", "reviewed": 8, "corrected": 0},
            {"field_name": "sender", "reviewed": 8, "corrected": 0},
        ],
    }
    found = {(i["pattern_type"], i["field_name"], i["digit_swap"] or i["source"] or i["matched_field"]): i for i in body["insights"]}
    assert set(found) == {
        ("frequent_correction", "commitment_number", None),
        ("silent_error", "commitment_number", None),
        ("digit_confusion", "commitment_number", "2>8"),
        ("better_source", "commitment_number", "barcode"),
    }
    swap = found[("digit_confusion", "commitment_number", "2>8")]
    assert (swap["event_count"], swap["reviewed_count"], swap["share"], swap["support"]) == (8, 8, 1.0, "low")
    assert swap["concentrated_in"] == {"form_type": "clalit", "sender": "כללית", "written_as": "handwritten"}
    assert swap["recommendation"] == "בשדה מספר התחייבות הספרה 8 נקראה שוב ושוב כ-2 – מומלץ לבדוק את איכות הסריקה ואת קריאת הספרות האלה"
    assert datetime.fromisoformat(swap["first_seen"]) <= datetime.fromisoformat(swap["last_seen"])
    _assert_no_values(response)


def test_filters_and_coverage(client):
    from db import queries

    for _ in range(8):
        _reviewed_form(queries)
    untouched = make_form(queries, file_hash="untouched")
    queries.save_extraction(untouched, [{"field_name": "id_number", "value": "000000018", "status": "verified"},
                                        {"field_name": "first_name", "value": "ישראלה", "status": "uncertain"}])

    body = client.get(_URL, params={"field_name": "id_number"}).json()
    assert body["field_name"] == "id_number"
    assert body["status"] == "insufficient_data"  # 8 reviewed id numbers < 20
    assert body["coverage"]["auto_accepted_fields"] == 1  # the untouched verified id number

    later = client.get(_URL, params={"since": "2999-01-01T00:00:00"}).json()
    assert later["status"] == "insufficient_data" and later["coverage"]["reviewed_fields"] == 0
    # A time with a zone is read as that moment in UTC.
    assert client.get(_URL, params={"until": "2999-01-01T02:00:00+02:00"}).json()["until"] == "2999-01-01T00:00:00"


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"since": "2026-02-01T00:00:00", "until": "2026-01-01T00:00:00"}, 400),
        ({"field_name": "diagnosis"}, 400),
        ({"since": "yesterday"}, 422),
    ],
)
def test_invalid_requests(client, params, status):
    response = client.get(_URL, params=params)
    assert response.status_code == status
    assert response.json()["detail"]


def test_meta_has_the_insight_labels(client):
    meta = client.get("/meta").json()
    assert set(meta["insight_patterns"]) >= {"digit_confusion", "wrong_field", "silent_error"}
    assert set(meta["insight_support_levels"]) == {"low", "medium", "high"}
    assert meta["form_types"]["clalit"] == "כללית" and meta["written_as_labels"]["handwritten"] == "כתב יד"


# ── The calculation itself (no DB) ──────────────────────────────────────────


def _event(field_name, change_kind, minute, **extra):
    return {"field_name": field_name, "change_kind": change_kind, "before_origin": "machine", "before_status": "conflict",
            "before_sources": "llm", "correct_seen_by": None, "matched_field": None, "digit_swaps": None,
            "before_written_as": None, "form_type": None, "sender": None,
            "created_at": datetime(2026, 10, 22, 9, minute), **extra}


def test_build_insights_patterns_and_thresholds(monkeypatch):
    import config
    from services.insights_service import build_insights

    monkeypatch.setattr(config, "INSIGHTS_MIN_REVIEWED_FIELDS", 10)
    events = (
        [_event("commitment_number", "wrong_field", i, matched_field="central_number", form_type="leumit") for i in range(3)]
        + [_event("received_date", "day_month_swap", 10 + i) for i in range(3)]
        + [_event("central_number", "filled_missing", 20 + i) for i in range(3)]
        + [_event("commitment_number", "removed", 30 + i) for i in range(2)]  # 2 < INSIGHTS_MIN_EVENTS: not reported
        + [_event("id_number", "none", 40 + i) for i in range(20)]  # approvals: reviewed, never a pattern
        + [_event("id_number", "typo", 59, before_origin="manual")]  # her own value changed: not counted at all
    )
    result = build_insights(events)
    assert result["coverage"]["reviewed_fields"] == 31
    found = {(i["pattern_type"], i["field_name"]): i for i in result["insights"]}
    assert set(found) == {
        ("wrong_field", "commitment_number"), ("frequent_correction", "commitment_number"),
        ("frequent_correction", "received_date"), ("day_month_swap", "received_date"),
        ("missed_value", "central_number"),
    }
    wrong = found[("wrong_field", "commitment_number")]
    assert (wrong["matched_field"], wrong["share"], wrong["concentrated_in"]["form_type"]) == ("central_number", 0.6, "leumit")
    assert wrong["first_seen"] == datetime(2026, 10, 22, 9, 0) and wrong["last_seen"] == datetime(2026, 10, 22, 9, 2)
    assert "מספר מרכזי" in wrong["recommendation"]

    # A field corrected in only a small share of its reviewed values is not "often corrected".
    rare = [_event("id_number", "typo", 0) for _ in range(3)] + [_event("id_number", "none", 1) for _ in range(30)]
    assert build_insights(rare)["insights"] == []
