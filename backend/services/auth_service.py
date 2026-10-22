"""Login with a one-time code mailed to one mailbox (config.AUTH_EMAIL).

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
import ssl
import threading
import time
from email.message import EmailMessage

import config

logger = logging.getLogger(__name__)

_SECRET = (config.AUTH_SECRET or secrets.token_hex(32)).encode()
_lock = threading.Lock()
_pending: dict[str, float | int | str] = {}  # {"hash", "expires", "attempts", "sent"}


class AuthError(Exception):
    """A login step that failed in a way the user should be told about (Hebrew message)."""


class AuthNotConfiguredError(AuthError):
    pass


def _hash(code: str) -> str:
    return hmac.new(_SECRET, code.encode(), hashlib.sha256).hexdigest()


def _send_mail(code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"קוד כניסה למערכת אימות הטפסים: {code}"
    message["From"] = config.SMTP_FROM
    message["To"] = config.AUTH_EMAIL
    message.set_content(
        f"קוד הכניסה שלך: {code}\n\nהקוד תקף ל-{config.AUTH_CODE_TTL_MINUTES} דקות ולשימוש אחד.\n"
        "אם לא ביקשת קוד – אפשר להתעלם מההודעה."
    )
    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS, context=context) as smtp:
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls(context=context)
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)


def masked_email(address: str | None = None) -> str:
    """A mailbox, partly hidden, for the login screen ("ad***@domain.org"). Default: config.AUTH_EMAIL."""
    name, _, domain = (address if address is not None else config.AUTH_EMAIL).strip().partition("@")
    return f"{name[:2]}***@{domain}" if name and domain else ""


def request_code(email: str | None = None) -> str:
    """Send a code; returns the (masked) address it went to. In demo mode (config.AUTH_DEMO_CODE) nothing is sent:
    the typed address is only echoed back and the fixed code becomes the pending one."""
    demo = bool(config.AUTH_DEMO_CODE)
    if demo and not masked_email(email or ""):
        raise AuthError("יש להזין כתובת מייל תקינה")
    if not demo and not (config.AUTH_EMAIL and config.SMTP_HOST and config.SMTP_USERNAME and config.SMTP_PASSWORD):
        raise AuthNotConfiguredError("שליחת קוד לא הוגדרה בשרת (AUTH_EMAIL / SMTP_*)")
    now = time.time()
    with _lock:
        wait = float(_pending.get("sent", 0)) + config.AUTH_CODE_RESEND_SECONDS - now
        if wait > 0:
            raise AuthError(f"קוד נשלח זה עתה – אפשר לבקש קוד חדש בעוד {int(wait) + 1} שניות")
        code = config.AUTH_DEMO_CODE or f"{secrets.randbelow(1_000_000):06d}"
        _pending.clear()
        _pending.update(hash=_hash(code), expires=now + config.AUTH_CODE_TTL_MINUTES * 60, attempts=0, sent=now)
    if demo:
        logger.info("Login code requested (demo mode — no mail sent)")
        return masked_email(email)
    try:
        _send_mail(code)
    except (smtplib.SMTPException, OSError) as exc:
        with _lock:
            _pending.clear()
        logger.error("Login code mail failed: %s", type(exc).__name__)
        raise AuthError("שליחת המייל נכשלה – בדקי את הגדרות ה-SMTP בשרת") from None
    logger.info("Login code sent")
    return masked_email()


def verify_code(code: str) -> str:
    """The session token for a correct code (the code is then used up)."""
    code = (code or "").strip()
    with _lock:
        if not _pending or time.time() > float(_pending["expires"]):
            _pending.clear()
            raise AuthError("אין קוד בתוקף – יש לבקש קוד חדש")
        _pending["attempts"] = int(_pending["attempts"]) + 1
        if not hmac.compare_digest(_hash(code), str(_pending["hash"])):
            if int(_pending["attempts"]) >= config.AUTH_CODE_MAX_ATTEMPTS:
                _pending.clear()
                raise AuthError("יותר מדי ניסיונות שגויים – יש לבקש קוד חדש")
            raise AuthError("הקוד שגוי")
        _pending.clear()
    logger.info("Login succeeded")
    return create_session()


def create_session() -> str:
    expires = str(int(time.time() + config.AUTH_SESSION_HOURS * 3600))
    signature = hmac.new(_SECRET, expires.encode(), hashlib.sha256).digest()
    return f"{expires}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def session_is_valid(token: str | None) -> bool:
    expires, _, signature = (token or "").partition(".")
    if not expires.isdigit() or not signature:
        return False
    expected = base64.urlsafe_b64encode(hmac.new(_SECRET, expires.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return hmac.compare_digest(signature, expected) and int(expires) > time.time()
