"""The pending one-time login code. Each operation is one transaction, so the code works the same from any replica
and a double click can't be counted twice."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from db.models import LoginCode

VerifyResult = Literal["ok", "none", "wrong", "too_many"]


class LoginCodeRepository:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def issue(self, code_hash: str, salt: str, now: datetime, ttl: timedelta, resend_after: timedelta) -> float:
        """Make this the pending code (the previous one, if any, is void) — unless the last code was sent less than
        `resend_after` ago: then nothing changes and the seconds left to wait are returned (0 = issued).
        Expired codes are deleted on the way."""
        with self._sessions() as session, session.begin():
            last_sent = session.execute(select(LoginCode.sent_at).order_by(LoginCode.sent_at.desc()).limit(1)).scalar()
            if last_sent is not None and last_sent + resend_after > now:
                return (last_sent + resend_after - now).total_seconds()
            session.execute(delete(LoginCode))
            session.add(LoginCode(code_hash=code_hash, salt=salt, attempts=0, sent_at=now, expires_at=now + ttl))
            return 0.0

    def verify(self, matches: Callable[[str, str], bool], now: datetime, max_attempts: int) -> VerifyResult:
        """Check an entered code against the pending one (matches(code_hash, salt)), counting the attempt.
        "ok" uses the code up; "none" = no valid code (an expired one is deleted); "too_many" voids it."""
        with self._sessions() as session, session.begin():
            session.execute(delete(LoginCode).where(LoginCode.expires_at < now))
            # Locked until the transaction ends (PostgreSQL: SELECT … FOR UPDATE; SQLite serializes writes anyway).
            pending = session.execute(select(LoginCode).order_by(LoginCode.id.desc()).limit(1).with_for_update()).scalar()
            if pending is None:
                return "none"
            pending.attempts += 1
            if matches(pending.code_hash, pending.salt):
                session.delete(pending)
                return "ok"
            if pending.attempts >= max_attempts:
                session.delete(pending)
                return "too_many"
            return "wrong"

    def discard(self) -> None:
        """Void the pending code (e.g. its mail could not be sent)."""
        with self._sessions() as session, session.begin():
            session.execute(delete(LoginCode))
