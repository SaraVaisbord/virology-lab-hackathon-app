"""Extraction & verification tests. All data is synthetic (no real patient data)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from db.constants import EXTRACTION_ERRORS, FIELDS, OCR_UNAVAILABLE_REASON, REASONS
from services.extraction_service import build_fields, match_sender
from tests.conftest import DummyUpload, make_form, png_bytes

VALID_ID = "000000018"
SENDERS = ["המרכז הרפואי שמיר", "כללית"]


def _by_name(fields, name):
    return [f for f in fields if f["field_name"] == name]


def _barcode(data, x=0.1, y=0.2):
    return {"data": data, "type": "CODE128", "x": x, "y": y, "width": 0.05, "height": 0.03, "page": 1}


# ── build_fields: verification rules ─────────────────────────────────────────


def test_every_missing_field_is_reported_not_found():
    fields = build_fields({}, [], SENDERS, page=1)
    assert [f["field_name"] for f in fields] == list(FIELDS)
    assert all(f["status"] == "not_found" and f["reason"] == REASONS["not_found"] for f in fields)


def test_barcode_match_confirms_reading_but_not_field_assignment():
    """Spec 3: a number is not classified as a commitment number just because a barcode reads it."""
    llm = {"commitment_number": [{"value": "2646", "confidence": "high", "label": "מספר התחייבות", "box_2d": [100, 100, 200, 300]}]}
    (field,) = _by_name(build_fields(llm, [_barcode("2646")], SENDERS), "commitment_number")

    assert field["status"] == "unverified"  # value reading agrees, assignment has no independent (OCR) proof
    assert field["reason"] == REASONS["assignment_llm_only"]
    assert field["barcode_value"] == "2646" and field["llm_value"] == "2646"
    assert field["evidence"]["agreement"] == "agree"
    assert field["evidence"]["assignment"]["label_supports"] is True


def test_same_number_in_central_and_commitment_is_a_conflict_on_both():
    """Spec 4: a central/commitment mismatch must not disappear when results are merged."""
    llm = {
        "central_number": [{"value": "555123", "confidence": "high"}],
        "commitment_number": [{"value": "555123", "confidence": "high"}],
    }
    fields = build_fields(llm, [_barcode("555123")], SENDERS)
    (central,) = _by_name(fields, "central_number")
    (commitment,) = _by_name(fields, "commitment_number")

    assert central["status"] == commitment["status"] == "conflict"
    assert central["evidence"]["assignment"]["also_claimed_by"] == ["commitment_number"]
    assert commitment["evidence"]["assignment"]["also_claimed_by"] == ["central_number"]
    assert "מספר התחייבות" in central["reason"] and "מספר מרכזי" in commitment["reason"]


def test_label_pointing_to_the_other_field_is_a_conflict():
    llm = {"central_number": [{"value": "947768", "confidence": "high", "label": "מספר התחייבות"}]}
    (field,) = _by_name(build_fields(llm, [], SENDERS), "central_number")
    assert field["status"] == "conflict"
    assert field["evidence"]["assignment"]["label_supports"] is False


def test_near_barcode_match_is_a_conflict_and_keeps_both_values():
    llm = {"commitment_number": [{"value": "555124", "confidence": "high"}]}
    (field,) = _by_name(build_fields(llm, [_barcode("555123")], SENDERS), "commitment_number")

    assert field["status"] == "conflict"
    assert field["llm_value"] == "555124" and field["barcode_value"] is None
    assert field["evidence"]["barcode_candidates"] == [
        {"data": "555123", "type": "CODE128", "match": "near", "box": {"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.03}}
    ]
    assert "555123" in field["reason"]


def test_multiple_numbers_are_kept_without_overwriting():
    """Spec 5."""
    llm = {"commitment_number": [
        {"value": "111111", "confidence": "high"},
        {"value": "222222", "confidence": "high"},
        {"value": "333333", "confidence": "low"},
    ]}
    values = [f["llm_value"] for f in _by_name(build_fields(llm, [_barcode("222222")], SENDERS), "commitment_number")]
    assert values == ["111111", "222222", "333333"]


def test_high_confidence_alone_never_verifies():
    llm = {"first_name": [{"value": "דנה", "confidence": "high"}], "central_number": [{"value": "12345", "confidence": "high"}]}
    fields = build_fields(llm, [], SENDERS)
    assert all(f["status"] != "verified" for f in fields)
    (central,) = _by_name(fields, "central_number")
    assert central["status"] == "unverified" and central["reason"] == REASONS["single_source"]


def test_id_number_verified_only_with_barcode_agreement_and_valid_checksum():
    llm = {"id_number": [{"value": "000-000-018", "confidence": "high"}]}
    (alone,) = _by_name(build_fields(llm, [], SENDERS), "id_number")
    assert alone["status"] == "unverified" and alone["value"] == VALID_ID and alone["llm_value"] == "000-000-018"

    (with_barcode,) = _by_name(build_fields(llm, [_barcode(VALID_ID)], SENDERS), "id_number")
    assert with_barcode["status"] == "verified" and with_barcode["box_source"] == "barcode"

    (bad,) = _by_name(build_fields({"id_number": [{"value": "123456789", "confidence": "high"}]}, [], SENDERS), "id_number")
    assert bad["status"] == "uncertain" and REASONS["invalid_id_checksum"] in bad["reason"]


def test_original_values_are_kept_while_normalizing():
    recent = (date.today() - timedelta(days=2)).strftime("%d.%m.%Y")
    llm = {"received_date": [{"value": recent, "confidence": "high"}], "sender": [{"value": "המרכז הרפואי שמיר (אסף הרופא)", "confidence": "high"}]}
    fields = build_fields(llm, [], SENDERS)
    (received,) = _by_name(fields, "received_date")
    (sender,) = _by_name(fields, "sender")
    assert received["llm_value"] == recent and received["value"] == recent.replace(".", "/")
    assert sender["llm_value"] == "המרכז הרפואי שמיר (אסף הרופא)" and sender["value"] == "המרכז הרפואי שמיר"


def test_implausible_received_date_is_uncertain():
    (field,) = _by_name(build_fields({"received_date": [{"value": "10/08/2020", "confidence": "high"}]}, [], SENDERS), "received_date")
    assert field["status"] == "uncertain" and REASONS["implausible_date"] in field["reason"]


def test_box_source_is_recorded():
    """Spec 7: the source of the location is kept."""
    llm = {"central_number": [
        {"value": "777777", "confidence": "high", "box_2d": [10, 20, 30, 60]},
        {"value": "888888", "confidence": "high", "box_2d": [10, 20, 30, 60]},
    ]}
    from_barcode, from_llm = _by_name(build_fields(llm, [_barcode("777777")], SENDERS), "central_number")
    assert from_barcode["box_source"] == "barcode" and from_barcode["x"] == 0.1
    assert from_llm["box_source"] == "llm" and (from_llm["x"], from_llm["y"]) == (0.02, 0.01)
    assert from_llm["evidence"]["llm"]["box"]["width"] == pytest.approx(0.04)


def test_single_value_field_with_alternatives_is_uncertain():
    llm = {"first_name": [{"value": "דנה", "confidence": "high"}, {"value": "דינה", "confidence": "medium"}]}
    (field,) = _by_name(build_fields(llm, [], SENDERS), "first_name")
    assert field["status"] == "uncertain" and field["evidence"]["llm_alternatives"] == ["דינה"]


def test_sender_matching():
    assert match_sender("המרכז הרפואי שמיר (אסף הרופא) - מחלקה פנימית ג'", SENDERS) == "המרכז הרפואי שמיר"
    assert match_sender("בית חולים לא קיים", SENDERS) is None


# ── Pipeline: sources are called and stored separately ───────────────────────


def _uploaded_form(queries, upload_service):
    form_id = upload_service.process_upload(DummyUpload("a.png", png_bytes()))["form_ids"][0]
    return form_id, queries.claim_next_form()


def test_pipeline_calls_every_source_and_stores_results_separately(app_env, monkeypatch):
    """Spec 1, 2, 7, 8."""
    import ai_extractor
    import barcode_reader
    from db import queries
    from services import extraction_service, upload_service

    calls = []
    monkeypatch.setattr(barcode_reader, "scan_image", lambda path: calls.append("barcode") or [_barcode("2646")])
    real_run_ocr = extraction_service.run_ocr
    monkeypatch.setattr(extraction_service, "run_ocr", lambda path, page: calls.append("ocr") or real_run_ocr(path, page))
    llm = {"commitment_number": [{"value": "2646", "confidence": "high", "label": "מספר התחייבות"}], "notes": "x"}
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda path, senders: calls.append("llm") or llm)

    form_id, form = _uploaded_form(queries, upload_service)
    extraction_service.extract_for_form(form)
    assert calls == ["barcode", "ocr", "llm"]

    stored = queries.get_form(form_id, with_sources=True)
    sources = stored["sources"]
    assert sources["llm_result"] == llm
    assert sources["barcode_result"]["status"] == "ok"
    assert sources["barcode_result"]["items"][0]["data"] == "2646" and sources["barcode_result"]["items"][0]["page"] == 1
    assert sources["ocr_result"] == {"status": "unavailable", "reason": OCR_UNAVAILABLE_REASON, "items": []}
    assert sources["source_errors"] is None

    (commitment,) = _by_name(stored["fields"], "commitment_number")
    assert commitment["llm_value"] == commitment["barcode_value"] == "2646" and commitment["ocr_value"] is None
    assert commitment["evidence"]["agreement"] == "agree" and commitment["box_source"] == "barcode"


def test_llm_failure_keeps_barcode_and_ocr_results(app_env, monkeypatch):
    """Spec 6."""
    import ai_extractor
    import barcode_reader
    from db import queries
    from services import upload_service
    from services.extraction_queue import ExtractionQueue

    monkeypatch.setattr(barcode_reader, "scan_image", lambda path: [_barcode("2646")])

    def broken(path, senders):
        raise ai_extractor.ExtractionError("Gemini API error: boom")

    monkeypatch.setattr(ai_extractor, "extract_from_image", broken)
    form_id, form = _uploaded_form(queries, upload_service)
    ExtractionQueue(1, 1).process(form)

    stored = queries.get_form(form_id, with_sources=True)
    assert stored["status"] == "failed" and stored["error"] == EXTRACTION_ERRORS["model"]
    assert stored["sources"]["barcode_result"]["items"][0]["data"] == "2646"
    assert stored["sources"]["ocr_result"]["status"] == "unavailable"
    assert stored["sources"]["source_errors"] == {"llm": EXTRACTION_ERRORS["model"]}


def test_barcode_failure_keeps_llm_result(app_env, monkeypatch):
    """Spec 6 (the other direction)."""
    import ai_extractor
    import barcode_reader
    from db import queries
    from services import extraction_service, upload_service

    def broken_scan(path):
        raise OSError("zbar missing")

    monkeypatch.setattr(barcode_reader, "scan_image", broken_scan)
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda path, senders: {"central_number": [{"value": "12345", "confidence": "high"}]})
    form_id, form = _uploaded_form(queries, upload_service)
    extraction_service.extract_for_form(form)

    stored = queries.get_form(form_id, with_sources=True)
    assert stored["status"] == "extracted"
    assert stored["sources"]["barcode_result"]["status"] == "error"
    assert stored["sources"]["source_errors"] == {"barcode": EXTRACTION_ERRORS["barcode"]}
    assert _by_name(stored["fields"], "central_number")[0]["llm_value"] == "12345"


def test_quota_error_requeues_form_and_pauses_queue(app_env, monkeypatch):
    import ai_extractor
    import barcode_reader
    from db import queries
    from services import upload_service
    from services.extraction_queue import ExtractionQueue

    monkeypatch.setattr(barcode_reader, "scan_image", lambda path: [])

    def rate_limited(path, senders):
        raise ai_extractor.QuotaExceededError("429", retry_after_seconds=120)

    monkeypatch.setattr(ai_extractor, "extract_from_image", rate_limited)
    form_id, form = _uploaded_form(queries, upload_service)
    queue = ExtractionQueue(1, 1)
    queue.process(form)

    assert queries.get_form(form_id)["status"] == "uploaded"
    # The queue isn't started in this test (state() would say "disabled"), so check the pause itself.
    assert queue._pause_reason == "quota" and queue._seconds_until_resume() > 0


def test_reverify_uses_stored_sources_without_calling_the_llm(app_env, monkeypatch):
    import ai_extractor
    from db import queries
    from services import extraction_service

    form_id = make_form(queries)
    queries.save_source_results(
        form_id,
        llm_result={"central_number": [{"value": "555123", "confidence": "high"}], "commitment_number": [{"value": "555123", "confidence": "high"}]},
        barcode_result={"status": "ok", "items": [_barcode("555123")]},
    )
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda *a: pytest.fail("LLM must not be called"))

    assert extraction_service.reverify_form(form_id) is True
    statuses = {f["field_name"]: f["status"] for f in queries.get_form(form_id)["fields"] if f["field_name"] in ("central_number", "commitment_number")}
    assert statuses == {"central_number": "conflict", "commitment_number": "conflict"}


def test_retry_delay_is_parsed_from_gemini_message():
    from ai_extractor import _retry_after_seconds

    assert _retry_after_seconds("Please retry in 3h40m34.49s.") == 3 * 3600 + 40 * 60 + 34.49
    assert _retry_after_seconds("Please retry in 13.2s") == 13.2


def test_invalid_model_json_does_not_leak_response_text(monkeypatch, tmp_path):
    """Errors are logged, so they must not contain the model's (possibly medical) output."""
    import ai_extractor

    class FakeResponse:
        text = '{"first_name": [{"value": "ישראל ישראלי"'

    class FakeModels:
        def generate_content(self, **kwargs):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    image = tmp_path / "p.png"
    image.write_bytes(png_bytes())
    monkeypatch.setattr(ai_extractor, "_get_client", lambda: FakeClient())
    with pytest.raises(ai_extractor.ExtractionError) as info:
        ai_extractor.extract_from_image(image, [])
    assert "ישראל" not in str(info.value)
