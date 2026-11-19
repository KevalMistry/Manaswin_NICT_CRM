"""WhatsApp delivery helper.

The institute mostly talks to students and guardians over WhatsApp, so fee
receipts and reminders can be delivered there as well as over email. This
module wraps the Meta WhatsApp Cloud API and stays disabled until
``WHATSAPP_TOKEN`` and ``WHATSAPP_PHONE_NUMBER_ID`` are configured, which keeps
local and test environments from messaging real phone numbers.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from app.core.config import (
    WHATSAPP_API_URL,
    WHATSAPP_API_VERSION,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
)


class WhatsAppNotConfigured(RuntimeError):
    """Raised when WhatsApp credentials are missing."""


class WhatsAppDeliveryError(RuntimeError):
    """Raised when a WhatsApp message cannot be delivered."""


def whatsapp_configured() -> bool:
    return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID)


def _api_url() -> str:
    if WHATSAPP_API_URL:
        return WHATSAPP_API_URL
    return (
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


def normalize_phone(phone: str | None) -> str | None:
    """Return digits only, keeping a leading country code.

    WhatsApp expects the number in international format without punctuation.
    A bare 10-digit Indian number is prefixed with 91 so local records work.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"91{digits}"
    elif digits.startswith("0") and len(digits) == 11:
        digits = f"91{digits[1:]}"
    return digits


def _post_message(payload: dict) -> None:
    request = urllib.request.Request(
        _api_url(),
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:200]
        raise WhatsAppDeliveryError(
            f"WhatsApp rejected the message: {detail or error.reason}"
        ) from error
    except OSError as error:
        raise WhatsAppDeliveryError("WhatsApp could not be reached.") from error


def send_whatsapp(phone: str | None, text: str) -> str:
    """Send a text message and return the normalised recipient number."""
    if not whatsapp_configured():
        raise WhatsAppNotConfigured(
            "WhatsApp delivery is not configured. Set WHATSAPP_TOKEN and "
            "WHATSAPP_PHONE_NUMBER_ID."
        )
    recipient = normalize_phone(phone)
    if not recipient:
        raise WhatsAppDeliveryError("This contact does not have a valid phone number.")
    _post_message(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text[:4000]},
        }
    )
    return recipient
