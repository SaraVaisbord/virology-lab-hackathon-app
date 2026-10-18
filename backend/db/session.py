from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]


def _normalize_database_url(database_url: str) -> str:
    if not database_url:
        raise ValueError("DATABASE_URL cannot be empty.")
    if database_url.startswith("sqlite"):
        parsed = urlsplit(database_url)
        if parsed.scheme != "sqlite":
            raise ValueError("DATABASE_URL must use the sqlite scheme when using SQLite.")
        db_path = parsed.path or ""
        if parsed.netloc:
            db_path = f"//{parsed.netloc}{db_path}"

        if db_path.startswith("/") and len(db_path) >= 3 and db_path[1].isalpha() and db_path[2] == ":":
            db_path = db_path[1:]

        if not Path(db_path).is_absolute():
            raise ValueError("SQLite DATABASE_URL must point to an absolute path.")
        return database_url
    return database_url


def _load_database_url() -> str:
    load_dotenv(BASE_DIR / ".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _normalize_database_url(database_url)

    data_dir = (BASE_DIR / "data").resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = (data_dir / "app.db").resolve()
    return f"sqlite:///{database_path.as_posix()}"


DATABASE_URL = _load_database_url()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _ensure_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        table_exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='extracted_fields'"
        ).fetchone()
        if table_exists is None:
            return

        existing_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(extracted_fields)").fetchall()
        }

        for column_name, column_type in {
            "ocr_value": "TEXT",
            "llm_value": "TEXT",
            "reason": "TEXT",
            "bbox": "TEXT",
            "page": "INTEGER",
            "x": "TEXT",
            "y": "TEXT",
            "width": "TEXT",
            "height": "TEXT",
        }.items():
            if column_name in existing_columns:
                continue
            conn.exec_driver_sql(f"ALTER TABLE extracted_fields ADD COLUMN {column_name} {column_type}")


_ensure_sqlite_schema()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
