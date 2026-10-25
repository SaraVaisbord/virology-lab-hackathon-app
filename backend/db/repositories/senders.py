"""The catalog of known senders (health funds, hospitals, labs …)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from db.models import Sender
from db.serialization import require_in
from domain.vocabulary import SENDER_KINDS


class SenderRepository:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def list_senders(self) -> list[tuple[str, str]]:
        with self._sessions() as session:
            rows = session.execute(select(Sender).order_by(Sender.name)).scalars().all()
            return [(row.name, row.kind) for row in rows]

    def names(self) -> list[str]:
        return [name for name, _kind in self.list_senders()]

    def add_sender(self, name: str, kind: str) -> int:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValueError("Sender name cannot be empty.")
        require_in(kind, SENDER_KINDS, "sender kind")

        with self._sessions() as session, session.begin():
            sender = Sender(name=normalized_name, kind=kind)
            session.add(sender)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError(f"Sender {normalized_name!r} already exists.") from exc
            return int(sender.id)
