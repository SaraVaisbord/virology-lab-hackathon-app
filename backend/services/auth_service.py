"""Login with a one-time code mailed to one mailbox (AuthSettings.email).

request_code() mails a 6-digit code; verify_code() checks it and returns a signed session token for the cookie.
The pending code lives in memory — the backend runs as a single process (one replica), and a restart only voids a
code nobody used yet. Only its hash is kept; codes, tokens and passwords never appear in logs or errors.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import smtplib
import threading
import time
from dataclasses import dataclass

from integrations.mailer import Mailer

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """A login step that failed in a way the user should be told about (Hebrew message)."""


class AuthNotConfiguredError(AuthError):
    pass


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    email: str  # the mailbox that receives the codes
    mail_configured: bool  # the SMTP server is set up
    demo_code: str  # DEMO ONLY: nothing is mailed and this fixed code always logs in
    secret: str  # signs session tokens; empty → a random one per run
    code_ttl_minutes: int
    code_max_attempts: int
    code_resend_seconds: int
    session_hours: int


def masked_email(address: str) -> str:
    """A mailbox, partly hidden, for the login screen ("ad***@domain.org")."""
    name, _, domain = address.strip().partition("@")
    return f"{name[:2]}***@{domain}" if name and domain else ""


class AuthService:
    def __init__(self, settings: AuthSettings, mailer: Mailer) -> None:
        self.settings = settings
        self._mailer = mailer
        self._secret = (settings.secret or secrets.token_hex(32)).encode()
        self._lock = threading.Lock()
        self._pending: dict[str, float | int | str] = {}  # {"hash", "expires", "attempts", "sent"}

    def _hash(self, code: str) -> str:
        return hmac.new(self._secret, code.encode(), hashlib.sha256).hexdigest()

    def masked_email(self) -> str:
        return masked_email(self.settings.email)

    def _send_code(self, code: str) -> None:
        self._mailer.send(
            self.settings.email,
            f"קוד כניסה למערכת אימות הטפסים: {code}",
            f"קוד הכניסה שלך: {code}\n\nהקוד תקף ל-{self.settings.code_ttl_minutes} דקות ולשימוש אחד.\n"
            "אם לא ביקשת קוד – אפשר להתעלם מההודעה.",
        )

    def request_code(self, email: str | None = None) -> str:
        """Send a code; returns the (masked) address it went to. In demo mode nothing is sent: the typed address is
        only echoed back and the fixed code becomes the pending one."""
        settings = self.settings
        demo = bool(settings.demo_code)
        if demo and not masked_email(email or ""):
            raise AuthError("יש להזין כתובת מייל תקינה")
        if not demo and not (settings.email and settings.mail_configured):
            raise AuthNotConfiguredError("שליחת קוד לא הוגדרה בשרת (AUTH_EMAIL / SMTP_*)")
        now = time.time()
        with self._lock:
            wait = float(self._pending.get("sent", 0)) + settings.code_resend_seconds - now
            if wait > 0:
                raise AuthError(f"קוד נשלח זה עתה – אפשר לבקש קוד חדש בעוד {int(wait) + 1} שניות")
            code = settings.demo_code or f"{secrets.randbelow(1_000_000):06d}"
            self._pending.clear()
            self._pending.update(hash=self._hash(code), expires=now + settings.code_ttl_minutes * 60, attempts=0, sent=now)
        if demo:
            logger.info("Login code requested (demo mode — no mail sent)")
            return masked_email(email or "")
        try:
            self._send_code(code)
        except (smtplib.SMTPException, OSError) as exc:
            with self._lock:
                self._pending.clear()
            logger.error("Login code mail failed: %s", type(exc).__name__)
            raise AuthError("שליחת המייל נכשלה – בדקי את הגדרות ה-SMTP בשרת") from None
        logger.info("Login code sent")
        return self.masked_email()

    def verify_code(self, code: str) -> str:
        """The session token for a correct code (the code is then used up)."""
        code = (code or "").strip()
        with self._lock:
            if not self._pending or time.time() > float(self._pending["expires"]):
                self._pending.clear()
                raise AuthError("אין קוד בתוקף – יש לבקש קוד חדש")
            self._pending["attempts"] = int(self._pending["attempts"]) + 1
            if not hmac.compare_digest(self._hash(code), str(self._pending["hash"])):
                if int(self._pending["attempts"]) >= self.settings.code_max_attempts:
                    self._pending.clear()
                    raise AuthError("יותר מדי ניסיונות שגויים – יש לבקש קוד חדש")
                raise AuthError("הקוד שגוי")
            self._pending.clear()
        logger.info("Login succeeded")
        return self.create_session()

    def create_session(self) -> str:
        expires = str(int(time.time() + self.settings.session_hours * 3600))
        signature = hmac.new(self._secret, expires.encode(), hashlib.sha256).digest()
        return f"{expires}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"

    def session_is_valid(self, token: str | None) -> bool:
        expires, _, signature = (token or "").partition(".")
        if not expires.isdigit() or not signature:
            return False
        expected = base64.urlsafe_b64encode(hmac.new(self._secret, expires.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        return hmac.compare_digest(signature, expected) and int(expires) > time.time()
