import importlib
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_alembic_config():
    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return cfg


def _reset_db_modules(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    import db.session as db_session
    import db.queries as queries

    importlib.reload(db_session)
    importlib.reload(queries)
    return db_session, queries


def test_migration_upgrade_and_downgrade_for_sqlite(tmp_path, monkeypatch):
    _reset_db_modules(tmp_path, monkeypatch)
    cfg = _make_alembic_config()

    command.upgrade(cfg, "head")
    with __import__("sqlalchemy", fromlist=["create_engine"]).create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        future=True,
    ).connect() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert {"forms", "extracted_fields", "senders"}.issubset(tables)

    command.downgrade(cfg, "base")
    with __import__("sqlalchemy", fromlist=["create_engine"]).create_engine(
        f"sqlite:///{tmp_path / 'app.db'}",
        future=True,
    ).connect() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert {"forms", "extracted_fields", "senders"}.isdisjoint(tables)
        assert tables <= {"alembic_version"}


def test_db_query_contract_and_status_updates(tmp_path, monkeypatch):
    _, queries = _reset_db_modules(tmp_path, monkeypatch)
    cfg = _make_alembic_config()
    command.upgrade(cfg, "head")

    form_id = queries.add_form(
        source_file="sample.pdf",
        file_hash="hash-123",
        page_number=1,
        image_path="/tmp/page1.png",
    )
    assert form_id > 0

    form = queries.get_form(form_id)
    assert form["status"] == "uploaded"
    assert form["error"] is None

    claimed = queries.claim_next_form()
    assert claimed is not None
    assert claimed["id"] == form_id
    assert claimed["status"] == "processing"

    queries.set_form_status(form_id, "failed", error="ocr failed")
    form = queries.get_form(form_id)
    assert form["status"] == "failed"
    assert form["error"] == "ocr failed"

    queries.set_form_status(form_id, "extracted", error=None)
    form = queries.get_form(form_id)
    assert form["status"] == "extracted"
    assert form["error"] is None

    queries.save_extraction(
        form_id=form_id,
        raw_llm_json='{"ok": true}',
        form_type="hospital",
        fields=[
            {"field_name": "sender", "value": "כללית", "raw_value": "כללית", "status": "verified"},
            {"field_name": "first_name", "value": "אבי", "raw_value": "אבי", "status": "verified"},
        ],
    )

    fields = queries.get_fields(form_id)
    assert len(fields) >= 2
    assert any(item["field_name"] == "sender" for item in fields)

    rows = queries.list_forms_with_fields(status="extracted", limit=10, offset=0)
    assert rows and rows[0]["id"] == form_id
    assert any(field["field_name"] == "sender" for field in rows[0]["fields"])

    sender_id = queries.add_sender("בריאות", "health_fund")
    assert sender_id > 0
    sender_list = queries.list_senders()
    assert any(name == "בריאות" for name, _ in sender_list)

    try:
        queries.select_rows("forms", limit=0)
        raise AssertionError("Expected ValueError for limit=0")
    except ValueError:
        pass

    all_rows = queries.select_rows("forms", limit=10)
    assert any(row["id"] == form_id for row in all_rows)
