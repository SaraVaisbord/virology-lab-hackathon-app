"""Extraction & verification tests. All data is synthetic (no real patient data)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from domain.vocabulary import EXTRACTION_ERRORS, FIELDS, OCR_UNAVAILABLE_REASON, REASONS
from domain.verification import VerificationRules, match_sender
from domain.verification import build_fields as _build_fields
from tests.conftest import DummyUpload, make_form, png_bytes

VALID_ID = "000000018"
SENDERS = ["המרכז הרפואי שמיר", "כללית"]
RULES = VerificationRules(received_date_max_age_days=365, local_ocr_min_confidence=60)


def build_fields(llm, barcodes, senders, **kwargs):
    return _build_fields(llm, barcodes, senders, RULES, **kwargs)


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
    assert field["status"] == "uncertain" and field["evidence"]["alternatives"] == ["דינה"]


def test_sender_matching():
    assert match_sender("המרכז הרפואי שמיר (אסף הרופא) - מחלקה פנימית ג'", SENDERS) == "המרכז הרפואי שמיר"
    assert match_sender("בית חולים לא קיים", SENDERS) is None


# ── build_fields: merging local (OCR) candidates ─────────────────────────────


def _local(field, value, source="ocr", label="מספר התחייבות", confidence=90):
    return {"field": field, "value": value, "raw": value, "source": source, "confidence": confidence, "rank": 0,
            "box": {"x": 0.3, "y": 0.4, "width": 0.1, "height": 0.02}, "label": label, "label_box": {}, "distance": 0.02}


def test_ocr_label_plus_two_readings_verifies_a_lookalike_number():
    llm = {"commitment_number": [{"value": "2646", "confidence": "high"}]}
    (field,) = _by_name(build_fields(llm, [_barcode("2646")], SENDERS, local_candidates=[_local("commitment_number", "2646")]), "commitment_number")
    assert field["status"] == "verified"
    assert field["evidence"]["sources"] == ["barcode", "llm", "ocr"]
    assert field["evidence"]["assignment"]["ocr_label"] == "מספר התחייבות"
    assert (field["llm_value"], field["ocr_value"], field["barcode_value"]) == ("2646", "2646", "2646")


def test_llm_and_ocr_label_disagree_on_the_field_is_a_conflict():
    llm = {"central_number": [{"value": "947768", "confidence": "high"}]}
    fields = build_fields(llm, [], SENDERS, local_candidates=[_local("commitment_number", "947768")])
    (central,) = _by_name(fields, "central_number")
    (commitment,) = _by_name(fields, "commitment_number")
    assert central["status"] == commitment["status"] == "conflict"
    assert "מספר התחייבות" in central["reason"] and "מספר מרכזי" in commitment["reason"]


def test_local_only_value_is_unverified_until_a_second_source_agrees():
    fields = build_fields(None, [], SENDERS, local_candidates=[_local("central_number", "12043017", label="מרכזי:")])
    (alone,) = _by_name(fields, "central_number")
    assert alone["status"] == "unverified" and alone["reason"] == REASONS["local_only"]
    assert alone["llm_value"] is None and alone["ocr_value"] == "12043017" and alone["box_source"] == "ocr"

    with_barcode = build_fields(None, [_barcode("12043017")], SENDERS, local_candidates=[_local("central_number", "12043017", label="מרכזי:")])
    assert _by_name(with_barcode, "central_number")[0]["status"] == "verified"  # OCR label + OCR & barcode readings


def test_low_confidence_ocr_only_value_is_uncertain():
    local = [_local("central_number", "12043017", label="מרכזי:", confidence=40)]
    (field,) = _by_name(build_fields(None, [], SENDERS, local_candidates=local), "central_number")
    assert field["status"] == "uncertain"


def test_ocr_and_llm_dates_merge_on_the_normalized_value():
    recent = date.today() - timedelta(days=2)
    llm = {"received_date": [{"value": recent.strftime("%d.%m.%Y"), "confidence": "high"}]}
    local = [{**_local("received_date", recent.strftime("%d/%m/%Y"), label="ת.קבלה"), "raw": recent.strftime("%d.%m.%y")}]
    (field,) = _by_name(build_fields(llm, [], SENDERS, local_candidates=local), "received_date")
    assert field["status"] == "verified" and field["value"] == recent.strftime("%d/%m/%Y")


# ── Pipeline: sources are called and stored separately ───────────────────────


@pytest.fixture
def fake_local_sources(monkeypatch):
    """Replace zbar / Tesseract with canned answers (fast, deterministic); records the order of calls."""
    import barcode_reader
    import local_extractor

    state = {"calls": [], "barcodes": [_barcode("2646")], "local": []}

    def scan(image):
        state["calls"].append("barcode")
        return [dict(b) for b in state["barcodes"]]

    class Result:
        def as_dict(self):
            return {"candidates": state["local"], "labels": [], "unassigned_numbers": []}

    def extract(views, barcodes):
        state["calls"].append("ocr")
        return Result()

    monkeypatch.setattr(barcode_reader, "scan_pil_image", scan)
    monkeypatch.setattr(local_extractor, "extract", extract)
    return state


def _uploaded_form(queries, upload_service):
    form_id = upload_service.process_upload(DummyUpload("a.png", png_bytes()))["form_ids"][0]
    return form_id, queries.claim_next_form()


def test_pipeline_calls_every_source_and_stores_results_separately(app_env, monkeypatch, fake_local_sources):
    """Spec 1, 2, 7, 8."""
    import ai_extractor
    from db import queries
    from services import extraction_service, upload_service

    fake_local_sources["local"] = [_local("commitment_number", "2646")]
    llm = {"commitment_number": [{"value": "2646", "confidence": "high", "label": "מספר התחייבות"}], "notes": "x"}
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda path, senders: fake_local_sources["calls"].append("llm") or llm)

    form_id, form = _uploaded_form(queries, upload_service)
    extraction_service.extract_for_form(form, use_llm=True)
    assert fake_local_sources["calls"][-2:] == ["ocr", "llm"] and "barcode" in fake_local_sources["calls"]

    stored = queries.get_form(form_id, with_sources=True)
    sources = stored["sources"]
    assert sources["llm_result"] == llm
    assert sources["barcode_result"]["status"] == "ok" and sources["barcode_result"]["items"][0]["data"] == "2646"
    assert sources["barcode_result"]["items"][0]["page"] == 1
    assert sources["ocr_result"]["status"] == "ok" and sources["ocr_result"]["candidates"][0]["value"] == "2646"
    assert sources["source_errors"] is None

    (commitment,) = _by_name(stored["fields"], "commitment_number")
    assert commitment["status"] == "verified"
    assert commitment["llm_value"] == commitment["barcode_value"] == commitment["ocr_value"] == "2646"


def test_local_only_mode_never_calls_the_llm(app_env, monkeypatch, fake_local_sources):
    import ai_extractor
    from db import queries
    from services import extraction_service, upload_service

    fake_local_sources["local"] = [_local("central_number", "12043017", label="מרכזי:")]
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda *a: pytest.fail("LLM must not be called"))
    form_id, form = _uploaded_form(queries, upload_service)
    extraction_service.extract_for_form(form, use_llm=False)

    stored = queries.get_form(form_id, with_sources=True)
    assert stored["status"] == "extracted" and stored["sources"]["llm_result"] is None
    assert _by_name(stored["fields"], "central_number")[0]["ocr_value"] == "12043017"


def test_llm_failure_keeps_barcode_and_ocr_results(app_env, monkeypatch, fake_local_sources):
    """Spec 6."""
    import ai_extractor
    from db import queries
    from services import upload_service
    from services.extraction_queue import ExtractionQueue

    def broken(path, senders):
        raise ai_extractor.ExtractionError("Gemini API error: boom")

    monkeypatch.setattr(ai_extractor, "extract_from_image", broken)
    monkeypatch.setattr("config.LLM_ENABLED", True)
    form_id, form = _uploaded_form(queries, upload_service)
    ExtractionQueue(1, 1).process(form)

    stored = queries.get_form(form_id, with_sources=True)
    assert stored["status"] == "failed" and stored["error"] == EXTRACTION_ERRORS["model"]
    assert stored["sources"]["barcode_result"]["items"][0]["data"] == "2646"
    assert stored["sources"]["ocr_result"]["status"] == "ok"
    assert stored["sources"]["source_errors"] == {"llm": EXTRACTION_ERRORS["model"]}


def test_barcode_failure_keeps_other_results(app_env, monkeypatch, fake_local_sources):
    """Spec 6 (the other direction)."""
    import ai_extractor
    import barcode_reader
    from db import queries
    from services import extraction_service, upload_service

    def broken_scan(image):
        raise OSError("zbar missing")

    monkeypatch.setattr(barcode_reader, "scan_pil_image", broken_scan)
    monkeypatch.setattr(ai_extractor, "extract_from_image", lambda path, senders: {"central_number": [{"value": "12345", "confidence": "high"}]})
    form_id, form = _uploaded_form(queries, upload_service)
    extraction_service.extract_for_form(form, use_llm=True)

    stored = queries.get_form(form_id, with_sources=True)
    assert stored["status"] == "extracted"
    assert stored["sources"]["barcode_result"]["status"] == "error"
    assert stored["sources"]["source_errors"] == {"barcode": EXTRACTION_ERRORS["barcode"]}
    assert _by_name(stored["fields"], "central_number")[0]["llm_value"] == "12345"


def test_quota_error_requeues_form_and_pauses_queue(app_env, monkeypatch, fake_local_sources):
    import ai_extractor
    from db import queries
    from services import upload_service
    from services.extraction_queue import ExtractionQueue

    def rate_limited(path, senders):
        raise ai_extractor.ModelsUnavailableError("429", retry_after_seconds=120, reason="quota")

    monkeypatch.setattr(ai_extractor, "extract_from_image", rate_limited)
    monkeypatch.setattr("config.LLM_ENABLED", True)
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
    from integrations.llm.gemini import retry_after_seconds

    assert retry_after_seconds("Please retry in 3h40m34.49s.", 60) == 3 * 3600 + 40 * 60 + 34.49
    assert retry_after_seconds("Please retry in 13.2s", 60) == 13.2


def test_one_off_extraction_with_openai_provider(app_env, monkeypatch, fake_local_sources):
    import openai_extractor
    from db import queries
    from services import extraction_service, upload_service

    fake_local_sources["barcodes"] = []
    monkeypatch.setattr(openai_extractor, "extract_from_image",
                        lambda path, senders: {"central_number": [{"value": "12345", "confidence": "high"}], "_model": "gpt-test"})
    form_id = upload_service.process_upload(DummyUpload("a.png", png_bytes()))["form_ids"][0]

    assert extraction_service.extract_one(form_id, "openai", use_llm=True) == "extracted"
    stored = queries.get_form(form_id, with_sources=True)
    assert stored["sources"]["llm_result"]["_model"] == "gpt-test"
    assert _by_name(stored["fields"], "central_number")[0]["llm_value"] == "12345"


def test_unlabeled_ocr_reading_confirms_the_value_but_not_the_field():
    llm = {"central_number": [{"value": "66608489", "confidence": "high"}]}
    ocr_numbers = [{"value": "66608489", "raw": "66608489", "source": "ocr"}]
    (field,) = _by_name(build_fields(llm, [], SENDERS, ocr_numbers=ocr_numbers), "central_number")
    assert field["evidence"]["sources"] == ["llm", "ocr"] and field["evidence"]["agreement"] == "agree"
    assert field["status"] == "unverified" and field["reason"] == REASONS["assignment_llm_only"]


# ── lab definitions (2026-10-20) ─────────────────────────────────────────────


def _anchored_date(value, central):
    return {**_local("received_date", value, label=f"מתחת למספר המרכזי {central}"), "anchor": "central_number"}


def test_different_dates_under_central_numbers_go_to_the_lab_worker():
    first = (date.today() - timedelta(days=3)).strftime("%d/%m/%Y")
    second = (date.today() - timedelta(days=9)).strftime("%d/%m/%Y")
    llm = {"received_date": [{"value": first, "confidence": "high"}]}
    local = [_anchored_date(first, "111"), {**_anchored_date(second, "222"), "rank": 1}]
    (field,) = _by_name(build_fields(llm, [], SENDERS, local_candidates=local), "received_date")
    assert field["status"] == "uncertain"  # LLM + OCR agree on one date, but another central number has another date
    assert REASONS["received_dates_differ"].format(dates=f"{first}, {second}") in field["reason"]
    assert field["evidence"]["alternatives"] == [second]


def test_one_date_under_the_central_number_can_verify():
    day = (date.today() - timedelta(days=3)).strftime("%d/%m/%Y")
    llm = {"received_date": [{"value": day, "confidence": "high"}]}
    (field,) = _by_name(build_fields(llm, [], SENDERS, local_candidates=[_anchored_date(day, "111")]), "received_date")
    assert field["status"] == "verified" and field["evidence"]["ocr"]["anchor"] == "central_number"


def test_sample_label_supports_a_commitment_only_where_the_sample_is_the_commitment():
    from domain.verification import sample_is_commitment_on

    llm = {"commitment_number": [{"value": "7712345", "confidence": "high", "label": "מספר דגימה"}]}
    (declared,) = _by_name(build_fields(llm, [], SENDERS, sample_is_commitment=True), "commitment_number")
    (other,) = _by_name(build_fields(llm, [], SENDERS), "commitment_number")
    assert declared["evidence"]["assignment"]["label_supports"] is True
    assert other["evidence"]["assignment"]["label_supports"] is None
    # Leumit forms always; any other form when its own text says so (OCR)
    assert sample_is_commitment_on(None, "leumit") and not sample_is_commitment_on(None, "hospital")
    assert sample_is_commitment_on({"sample_is_commitment": True}, "hospital")


def test_case_label_no_longer_points_to_the_central_number():
    llm = {"commitment_number": [{"value": "12043017", "confidence": "high", "label": "מקרה"}]}
    (field,) = _by_name(build_fields(llm, [], SENDERS), "commitment_number")
    assert field["status"] != "conflict"
