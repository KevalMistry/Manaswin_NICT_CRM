"""Pluggable payment helpers for online admission registration fees.

The default provider is ``manual``: staff record the cash/UPI/bank payment in
the admin workspace and the applicant is never redirected to an external
gateway. The Razorpay path is entirely optional and stays dormant unless both
``ADMISSION_PAYMENT_PROVIDER=razorpay`` and the API keys are configured.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import (
    ADMISSION_PAYMENT_CURRENCY,
    ADMISSION_PAYMENT_PROVIDER,
    GST_RATE_PERCENT,
    RAZORPAY_API_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)


class PaymentGatewayError(RuntimeError):
    """Raised when an optional online gateway cannot be used."""


def provider_name() -> str:
    return ADMISSION_PAYMENT_PROVIDER


def gateway_configured() -> bool:
    return (
        ADMISSION_PAYMENT_PROVIDER == "razorpay"
        and bool(RAZORPAY_KEY_ID)
        and bool(RAZORPAY_KEY_SECRET)
    )


def currency() -> str:
    return ADMISSION_PAYMENT_CURRENCY


def gst_breakdown(amount: Decimal) -> tuple[Decimal, Decimal]:
    """Split a GST-inclusive amount into taxable value and GST.

    Matches the finance module's convention that stored fee amounts already
    include GST. Rounded to paise using half-up rounding.
    """
    rate = Decimal(str(GST_RATE_PERCENT))
    gross = Decimal(amount)
    taxable = (gross / (Decimal("1") + rate / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    gst = (gross - taxable).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return taxable, gst


def create_razorpay_order(
    amount: Decimal,
    receipt: str,
    notes: dict[str, str] | None = None,
) -> dict[str, object]:
    """Create a Razorpay order. Only called when the gateway is configured."""
    if not gateway_configured():
        raise PaymentGatewayError(
            "Online payments are not configured. Record the payment manually instead."
        )

    amount_paise = int((Decimal(amount) * Decimal("100")).to_integral_value())
    payload = json.dumps(
        {
            "amount": amount_paise,
            "currency": currency(),
            "receipt": receipt[:40],
            "notes": notes or {},
        }
    ).encode()
    credentials = base64.b64encode(
        f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode()
    ).decode()
    request = Request(
        f"{RAZORPAY_API_URL}/orders",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed gateway URL
            return json.loads(response.read().decode())
    except HTTPError as error:
        raise PaymentGatewayError(
            f"The payment gateway rejected the request (HTTP {error.code})."
        ) from error
    except (URLError, TimeoutError, ValueError) as error:
        raise PaymentGatewayError(
            "The payment gateway could not be reached. Try again later or pay at the branch."
        ) from error


def verify_razorpay_signature(
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    if not RAZORPAY_KEY_SECRET:
        return False
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def razorpay_key_id() -> str:
    return RAZORPAY_KEY_ID if gateway_configured() else ""
