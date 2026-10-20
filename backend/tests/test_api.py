from __future__ import annotations

import io

from openpyxl import load_workbook

from db.constants import FIELD_LABELS, FORM_STATUS_LABELS
from tests.conftest import make_form


def test_meta_exposes_vocabulary(client):
    meta = client.get("/meta").json()
    assert [f["key"] for f in meta["fields"]] == list(FIELD_LABELS)
    assert meta["form_statuses"] == FORM_STATUS_LABELS
    assert meta["page_size"] > 0


def test_list_is_paged_and_validated(client):
    from db import queries

    ids = [make_form(queries, file_hash=f"h{i}") for i in range(3)]
    body = client.get("/forms?limit=2").json()
    assert body["total"] == 3 and body["limit"] == 2
    assert [f["id"] for f in body["items"]] == ids[::-1][:2]

    assert client.get("/forms?limit=0").status_code == 422
    assert client.get("/forms?sort_by=nope").status_code == 400
    assert client.get("/forms?status=nope").status_code == 400


def test_confirm_field_endpoint(client):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "id_number", "value": "1", "status": "uncertain"}])
    field_id = queries.get_form(form_id)["fields"][0]["id"]

    response = client.patch(f"/forms/{form_id}/fields/{field_id}/confirm", json={"corrected_value": " 000000018 "})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved" and body["fields"][0]["value"] == "000000018"

    assert client.patch(f"/forms/{form_id}/fields/999/confirm", json={}).status_code == 404


def test_retry_and_summary(client):
    from db import queries

    form_id = make_form(queries)
    queries.set_form_status(form_id, "failed", error="x")
    assert client.post(f"/forms/{form_id}/retry").json()["status"] == "uploaded"
    assert client.get("/forms/summary").json()["pending"] == 1


def test_export_respects_filters_and_mode(client):
    from db import queries

    keep = make_form(queries, file_hash="keep")
    make_form(queries, file_hash="skip")
    queries.save_extraction(keep, [
        {"field_name": "commitment_number", "value": "1", "status": "verified"},
        {"field_name": "commitment_number", "value": "2", "status": "verified"},
    ])

    def rows(url):
        response = client.get(url)
        assert response.status_code == 200
        return list(load_workbook(io.BytesIO(response.content)).active.values)

    filtered = rows("/forms/export?mode=filtered&query=keep")
    assert len(filtered) == 2 and "1, 2" in filtered[1]
    assert len(rows("/forms/export?mode=all&query=keep")) == 3
    assert len(rows("/forms/export?mode=approved")) == 2  # keep is approved (all fields verified)
    assert client.get("/forms/export?mode=nope").status_code == 400


def test_source_evidence_reaches_the_api(client):
    """Spec 7/8: per-source results and per-field evidence survive until the API response."""
    from db import queries
    from services.extraction_service import build_fields

    form_id = make_form(queries)
    llm = {"commitment_number": [{"value": "2646", "confidence": "high", "label": "מספר התחייבות"}]}
    barcodes = [{"data": "2646", "type": "CODE39", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1, "page": 1}]
    queries.save_source_results(form_id, llm_result=llm, barcode_result={"status": "ok", "items": barcodes},
                                ocr_result={"status": "unavailable", "items": []})
    queries.save_extraction(form_id, build_fields(llm, barcodes, []))

    detail = client.get(f"/forms/{form_id}").json()
    assert detail["sources"]["llm_result"] == llm
    assert detail["sources"]["barcode_result"]["items"][0]["data"] == "2646"
    assert detail["sources"]["ocr_result"]["status"] == "unavailable"
    commitment = next(f for f in detail["fields"] if f["field_name"] == "commitment_number")
    assert commitment["llm_value"] == commitment["barcode_value"] == "2646"
    assert commitment["box_source"] == "barcode"
    assert commitment["evidence"]["agreement"] == "agree"

    listed = client.get("/forms").json()["items"][0]
    assert "sources" not in listed  # heavy raw results only on the detail endpoint
    assert listed["fields"][0]["evidence"] is not None or listed["fields"][0]["status"] == "not_found"


def test_disabled_worker_is_reported_in_summary(client):
    """With WORKER_ENABLED=false the queue never starts — the UI must be told why nothing is processed."""
    from db import queries

    make_form(queries)
    summary = client.get("/forms/summary").json()
    assert summary["pending"] == 1
    assert summary["queue"] == {"running": False, "paused_until": None, "pause_reason": "disabled"}


def test_manual_add_edit_delete_without_extraction(client):
    """The lab worker can fill a form by hand, whatever its extraction state."""
    from db import queries

    form_id = make_form(queries)  # still queued — never extracted
    body = client.post(f"/forms/{form_id}/fields", json={"field_name": "commitment_number", "value": " 2646 "}).json()
    body = client.post(f"/forms/{form_id}/fields", json={"field_name": "commitment_number", "value": "2647"}).json()
    commitments = [f for f in body["fields"] if f["field_name"] == "commitment_number"]
    assert [f["value"] for f in commitments] == ["2646", "2647"]
    assert all(f["status"] == "confirmed" and f["evidence"] == {"manual": True} for f in commitments)
    assert body["status"] == "uploaded"  # a manual edit doesn't take the form out of the queue

    # single-value field: one value only — a second one must be an edit
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "id_number", "value": "000000018"}).status_code == 200
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "id_number", "value": "1"}).status_code == 400
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "nope", "value": "1"}).status_code == 400
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "sender", "value": "  "}).status_code == 400

    # edit any value (even an already confirmed one), then delete one
    field_id = commitments[1]["id"]
    edited = client.patch(f"/forms/{form_id}/fields/{field_id}/confirm", json={"corrected_value": "2648"}).json()
    assert [f["value"] for f in edited["fields"] if f["field_name"] == "commitment_number"] == ["2646", "2648"]
    after = client.delete(f"/forms/{form_id}/fields/{field_id}").json()
    assert [f["value"] for f in after["fields"] if f["field_name"] == "commitment_number"] == ["2646"]
    assert client.delete(f"/forms/{form_id}/fields/{field_id}").status_code == 404


def test_manual_value_replaces_not_found_and_completes_a_failed_form(client):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "id_number", "status": "not_found"}])
    queries.set_form_status(form_id, "failed", error="x")
    body = client.post(f"/forms/{form_id}/fields", json={"field_name": "id_number", "value": "000000018"}).json()
    ids = [f for f in body["fields"] if f["field_name"] == "id_number"]
    assert [(f["value"], f["status"]) for f in ids] == [("000000018", "confirmed")]
    assert body["status"] == "approved"


def test_pick_a_page_number_into_a_field_keeps_its_location(client):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "id_number", "value": "1", "llm_value": "1", "status": "uncertain"}])
    box = {"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.02}

    picked = client.post(f"/forms/{form_id}/fields", json={
        "field_name": "commitment_number", "value": "947768", "box": box, "picked_from": "barcode"}).json()
    row = next(f for f in picked["fields"] if f["field_name"] == "commitment_number")
    assert (row["value"], row["status"], row["box_source"], row["x"]) == ("947768", "confirmed", "barcode", 0.1)
    assert row["evidence"] == {"manual": True, "picked_from": "barcode"}

    # single-value field: picking replaces the old value only when asked to
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "id_number", "value": "000000018"}).status_code == 400
    replaced = client.post(f"/forms/{form_id}/fields", json={
        "field_name": "id_number", "value": "000000018", "replace": True, "box": box, "picked_from": "ocr"}).json()
    ids = [f for f in replaced["fields"] if f["field_name"] == "id_number"]
    assert [(f["value"], f["box_source"]) for f in ids] == [("000000018", "ocr")]
    assert client.post(f"/forms/{form_id}/fields", json={"field_name": "sender", "value": "x", "picked_from": "nope"}).status_code == 400
