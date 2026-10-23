from __future__ import annotations

import os

# Must run before the settings are read: tests never load backend/.env (real API keys stay out of tests and output).
os.environ["APP_ENV"] = "test"
os.environ["AUTH_ENABLED"] = "0"  # login is tested on its own (test_auth.py); everything else runs logged-out
for _name in [n for n in os.environ if n.startswith(("GEMINI_API_KEY", "OPENAI_API_KEY", "OPEN_AI_API_KEY", "ANTHROPIC_API_KEY"))]:
    del os.environ[_name]

import io  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PIL import Image  # noqa: E402

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
def settings(tmp_path, monkeypatch):
    """Settings for an isolated data dir and a migrated database (SQLite in tmp_path, or TEST_DATABASE_URL)."""
    from config import load_settings

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    # TEST_DATABASE_URL=postgresql+psycopg://… runs the whole suite on PostgreSQL (as on AWS RDS); emptied per test.
    server_url = os.getenv("TEST_DATABASE_URL")
    if server_url:
        _empty_database(server_url)
    monkeypatch.setenv("DATABASE_URL", server_url or f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    monkeypatch.setenv("WORKER_ENABLED", "0")
    command.upgrade(alembic_config(), "head")  # alembic reads the same environment
    return load_settings()


@pytest.fixture
def make_container(settings):
    """make_container(**setting_overrides, mailer=..., storage=...) → the application's components (worker not
    started); databases are closed after the test."""
    from container import build_container

    built = []

    def make(mailer=None, storage=None, **overrides):
        container = build_container(replace(settings, **overrides), mailer=mailer, storage=storage)
        built.append(container)
        return container
    yield make
    for container in built:
        container.close()


@pytest.fixture
def container(make_container):
    return make_container()


@pytest.fixture
def client(container):
    from fastapi.testclient import TestClient

    from api.app import create_app

    return TestClient(create_app(container=container))


class Queries:
    """The repositories' methods by name, for tests: queries.add_form(...), queries.confirm_field(...), …"""

    def __init__(self, container) -> None:
        self._repositories = (container.forms, container.review, container.listing, container.history, container.senders)

    def __getattr__(self, name: str):
        for repository in self._repositories:
            if hasattr(repository, name):
                return getattr(repository, name)
        raise AttributeError(name)


@pytest.fixture
def queries(container):
    return Queries(container)


def png_bytes(size=(120, 80), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(255, 255, 255)).save(buffer, format=fmt)
    return buffer.getvalue()


def make_form(queries, file_hash: str = "hash-1", page_number: int = 1) -> int:
    return queries.add_form(source_file=f"{file_hash}.pdf", file_hash=file_hash, page_number=page_number, image_path=f"pages_img/{file_hash}_p{page_number}.png")
