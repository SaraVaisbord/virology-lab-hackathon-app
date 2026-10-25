"""Sending mail over SMTP (the login code). Credentials never appear in logs or errors."""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Raises smtplib.SMTPException / OSError when the mail could not be sent."""
        ...


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int  # 587 = STARTTLS, 465 = TLS from the start
    username: str
    password: str
    sender: str
    timeout_seconds: int

    @property
    def configured(self) -> bool:
        return bool(self.host and self.username and self.password)


class SmtpMailer:
    def __init__(self, settings: SmtpSettings) -> None:
        self.settings = settings

    def send(self, to: str, subject: str, body: str) -> None:
        settings = self.settings
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.sender
        message["To"] = to
        message.set_content(body)
        context = ssl.create_default_context()
        if settings.port == 465:
            with smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout_seconds, context=context) as smtp:
                smtp.login(settings.username, settings.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds) as smtp:
                smtp.starttls(context=context)
                smtp.login(settings.username, settings.password)
                smtp.send_message(message)
