from __future__ import annotations

import os

# Must run before config is imported: tests never load backend/.env (real API keys stay out of tests and output).
os.environ["APP_ENV"] = "test"
for _name in [n for n in os.environ if n.startswith(("GEMINI_API_KEY", "OPENAI_API_KEY", "OPEN_AI_API_KEY"))]:
    del os.environ[_name]

import importlib  # noqa: E402
import io  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _empty_database(url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """Isolated data dir + migrated SQLite DB; reloads modules that captured settings at import time."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    # TEST_DATABASE_URL=postgresql+psycopg://… runs the whole suite on PostgreSQL (as on AWS RDS); emptied per test.
    server_url = os.getenv("TEST_DATABASE_URL")
    if server_url:
        _empty_database(server_url)
    monkeypatch.setenv("DATABASE_URL", server_url or f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    monkeypatch.setenv("WORKER_ENABLED", "0")

    import config
    import db.queries
    import db.session
    import services.upload_service

    for module in (config, db.session, db.queries, services.upload_service):
        importlib.reload(module)

    command.upgrade(alembic_config(), "head")
    return data_dir


@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


class DummyUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


def png_bytes(size=(120, 80), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(255, 255, 255)).save(buffer, format=fmt)
    return buffer.getvalue()


def make_form(queries, file_hash: str = "hash-1", page_number: int = 1) -> int:
    return queries.add_form(source_file=f"{file_hash}.pdf", file_hash=file_hash, page_number=page_number, image_path=f"pages_img/{file_hash}_p{page_number}.png")
