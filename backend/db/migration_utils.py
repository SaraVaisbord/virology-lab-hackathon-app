"""Helpers for Alembic migrations that must run on both SQLite (local) and PostgreSQL (AWS RDS)."""

from __future__ import annotations

from alembic import op


def recreate_mode() -> str:
    """SQLite can't ALTER constraints, so batch migrations rebuild its tables ("always"). PostgreSQL alters tables in
    place ("auto") — rebuilding there fails, because the primary key of `forms` is referenced by `extracted_fields`."""
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"
