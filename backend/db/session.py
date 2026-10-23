from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


class Database:
    """One database: its engine and the session factory the repositories use. Created by the composition root."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30} if self.is_sqlite else {},
        )
        if self.is_sqlite:
            event.listen(self.engine, "connect", _set_sqlite_pragma)  # this engine only — never sent to PostgreSQL
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def dispose(self) -> None:
        self.engine.dispose()


def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
