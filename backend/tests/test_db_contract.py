from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine

from tests.conftest import alembic_config, make_form


def _tables(app_env) -> set[str]:
    import db.session

    engine = create_engine(db.session.DATABASE_URL, future=True)
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        return {row[0] for row in rows}


def test_migration_upgrade_and_downgrade(app_env):
    assert {"forms", "extracted_fields", "senders"} <= _tables(app_env)
    command.downgrade(alembic_config(), "base")
    assert _tables(app_env) <= {"alembic_version"}


def test_upgrade_preserves_existing_fields(app_env):
    """Batch table rebuilds must not cascade-delete child rows."""
    import db.session

    cfg = alembic_config()
    command.downgrade(cfg, "ea99c03b9c61")
    engine = create_engine(db.session.DATABASE_URL, future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO forms (id, source_file, file_hash, page_number, image_path, status) VALUES (1, 'a', 'h', 1, 'p', 'extracted')")
        conn.exec_driver_sql("INSERT INTO extracted_fields (form_id, field_name, raw_value, status) VALUES (1, 'first_name', 'אבי', 'uncertain')")

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT llm_value FROM extracted_fields").fetchall() == [("אבי",)]


def test_queue_claim_and_status_updates(app_env):
    from db import queries

    form_id = make_form(queries)
    assert queries.get_form(form_id)["status"] == "uploaded"

    claimed = queries.claim_next_form()
    assert claimed["id"] == form_id and claimed["status"] == "processing"
    assert queries.claim_next_form() is None

    queries.set_form_status(form_id, "failed", error="boom")
    assert queries.get_form(form_id)["error"] == "boom"

    queries.requeue_form(form_id)
    assert queries.get_form(form_id)["status"] == "uploaded"

    queries.claim_next_form()
    assert queries.requeue_stale_processing() == 1
    assert queries.get_form(form_id)["status"] == "uploaded"


def test_multi_value_confirm_and_approval(app_env):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(
        form_id,
        fields=[
            {"field_name": "commitment_number", "value": "111", "status": "uncertain"},
            {"field_name": "commitment_number", "value": "222", "status": "uncertain"},
            {"field_name": "first_name", "value": "אבי", "status": "verified"},
        ],
    )
    form = queries.get_form(form_id)
    assert form["status"] == "extracted"
    first, second = [f for f in form["fields"] if f["field_name"] == "commitment_number"]

    form = queries.confirm_field(form_id, first["id"], corrected_value="112")
    assert form["status"] == "extracted"
    confirmed = next(f for f in form["fields"] if f["id"] == first["id"])
    assert confirmed["value"] == "112" and confirmed["corrected_value"] == "112" and confirmed["status"] == "confirmed"

    form = queries.confirm_field(form_id, second["id"], corrected_value=None)
    assert form["status"] == "approved"

    with pytest.raises(LookupError):
        queries.confirm_field(form_id, 999999, corrected_value=None)


def test_re_extraction_keeps_human_corrections(app_env):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "id_number", "value": "1", "status": "uncertain"}])
    field_id = queries.get_form(form_id)["fields"][0]["id"]
    queries.confirm_field(form_id, field_id, corrected_value="000000018")

    queries.save_extraction(form_id, [{"field_name": "id_number", "value": "999", "status": "uncertain"}])
    fields = queries.get_form(form_id)["fields"]
    assert [f["value"] for f in fields] == ["000000018"]


def test_list_forms_paging_filtering_sorting(app_env):
    from db import queries

    ids = [make_form(queries, file_hash=f"h{i}") for i in range(5)]
    queries.save_extraction(ids[0], [{"field_name": "first_name", "value": "דנה", "status": "verified"}])

    page, total = queries.list_forms(queries.FormFilters(), limit=2)
    assert total == 5 and [f["id"] for f in page] == ids[::-1][:2]  # newest first

    page, total = queries.list_forms(queries.FormFilters(query="דנה"), limit=10)
    assert total == 1 and page[0]["id"] == ids[0]

    page, total = queries.list_forms(queries.FormFilters(column_filters={"first_name": "דנ"}), limit=10)
    assert [f["id"] for f in page] == [ids[0]]

    page, _ = queries.list_forms(queries.FormFilters(sort_by="id", sort_dir="asc"), limit=1, offset=1)
    assert page[0]["id"] == ids[1]

    page, _ = queries.list_forms(queries.FormFilters(sort_by="first_name", sort_dir="desc"), limit=1)
    assert page[0]["id"] == ids[0]

    with pytest.raises(ValueError):
        queries.list_forms(queries.FormFilters(sort_by="nope"), limit=1)


def test_summary_and_senders(app_env):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "sender", "value": "x", "status": "uncertain"}])
    make_form(queries, file_hash="other")

    summary = queries.forms_summary()
    assert summary["total"] == 2
    assert summary["pending"] == 1
    assert summary["by_status"]["extracted"] == 1
    assert summary["fields_to_review"] == 1

    assert queries.add_sender("בריאות", "health_fund") > 0
    assert ("בריאות", "health_fund") in queries.list_senders()


def test_upgrade_splits_combined_llm_and_barcode_results(app_env):
    """Revision c3d4e5f6a7b8: {"llm", "barcodes"} in raw_llm_json → llm_result + barcode_result; ocr_value → barcode_value."""
    import json

    import db.session

    cfg = alembic_config()
    command.downgrade(cfg, "b7c1d2e3f4a5")
    engine = create_engine(db.session.DATABASE_URL, future=True)
    combined = {"llm": {"commitment_number": [{"value": "2646"}]}, "barcodes": [{"data": "2646", "type": "CODE39"}]}
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO forms (id, source_file, file_hash, page_number, image_path, status, raw_llm_json) VALUES (1, 'a', 'h', 3, 'p', 'extracted', ?)",
            (json.dumps(combined),),
        )
        conn.exec_driver_sql("INSERT INTO extracted_fields (form_id, field_name, value, ocr_value, status) VALUES (1, 'commitment_number', '2646', '2646', 'verified')")
    engine.dispose()

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        llm, barcodes = conn.exec_driver_sql("SELECT llm_result, barcode_result FROM forms").one()
        field = conn.exec_driver_sql("SELECT barcode_value, ocr_value FROM extracted_fields").one()
    assert json.loads(llm) == combined["llm"]
    assert json.loads(barcodes) == {"status": "ok", "items": [{"data": "2646", "type": "CODE39", "page": 3}]}
    assert tuple(field) == ("2646", None)


def test_re_extraction_keeps_fields_confirmed_without_correction(app_env):
    from db import queries

    form_id = make_form(queries)
    queries.save_extraction(form_id, [{"field_name": "first_name", "value": "דנה", "status": "unverified"}])
    field_id = queries.get_form(form_id)["fields"][0]["id"]
    queries.confirm_field(form_id, field_id, corrected_value=None)  # approved as-is

    queries.save_extraction(form_id, [{"field_name": "first_name", "value": "דינה", "status": "uncertain"}])
    (field,) = queries.get_form(form_id)["fields"]
    assert (field["value"], field["status"]) == ("דנה", "confirmed")
