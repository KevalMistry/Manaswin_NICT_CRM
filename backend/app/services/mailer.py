"""Small SMTP helper shared by fee receipts and reminders.

Password-reset mail still lives in ``app.api.auth`` because it owns the reset
token lifecycle. Everything else can use this helper so the SMTP behaviour is
configured in one place.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import (
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)


class MailNotConfigured(RuntimeError):
    """Raised when SMTP settings are missing."""


class MailDeliveryError(RuntimeError):
    """Raised when the SMTP server rejects or cannot deliver a message."""


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_email(
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """Send a plain-text (optionally HTML) email with optional attachments.

    ``attachments`` items are ``(filename, content, mime_type)`` tuples.
    """
    if not smtp_configured():
        raise MailNotConfigured(
            "Email delivery is not configured. Set SMTP_HOST and SMTP_FROM."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    for filename, content, mime_type in attachments or []:
        if "/" not in mime_type:
            raise ValueError(f"Invalid attachment MIME type '{mime_type}'")
        maintype, subtype = mime_type.split("/", 1)
        message.add_attachment(
            content,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise MailDeliveryError(
            "The email could not be sent by the configured mail server."
        ) from error
