"""Student UPI payment helpers shared by the portal and staff review APIs."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fee import FeeInstallment, PaymentClaim


CLAIM_PENDING = "pending"
CLAIM_APPROVED = "approved"
CLAIM_REJECTED = "rejected"
CLAIM_CANCELLED = "cancelled"
CLAIM_STATUSES = (CLAIM_PENDING, CLAIM_APPROVED, CLAIM_REJECTED, CLAIM_CANCELLED)
REJECTION_CODES = (
    "not_received",
    "amount_mismatch",
    "invalid_reference",
    "wrong_branch",
    "duplicate",
    "other",
)


def paid_total(installment: FeeInstallment) -> Decimal:
    return sum((payment.amount for payment in installment.payments), Decimal("0"))


def pending_claim_total(
    db: Session, installment_id: int, exclude_claim_id: int | None = None
) -> Decimal:
    query = select(PaymentClaim).where(
        PaymentClaim.installment_id == installment_id,
        PaymentClaim.status == CLAIM_PENDING,
    )
    if exclude_claim_id is not None:
        query = query.where(PaymentClaim.id != exclude_claim_id)
    claims = db.scalars(query).all()
    return sum((claim.amount for claim in claims), Decimal("0"))


def remaining_amount(
    db: Session, installment: FeeInstallment, exclude_claim_id: int | None = None
) -> Decimal:
    remaining = installment.amount - paid_total(installment)
    return max(remaining, Decimal("0"))


def claimable_amount(
    db: Session, installment: FeeInstallment, exclude_claim_id: int | None = None
) -> Decimal:
    remaining = remaining_amount(db, installment)
    return max(remaining - pending_claim_total(db, installment.id, exclude_claim_id), Decimal("0"))


def upi_payment_uri(
    upi_id: str,
    payee_name: str,
    amount: Decimal,
    note: str,
) -> str:
    """Return a standard UPI deep link/QR payload with a fixed amount."""
    query = urlencode(
        {
            "pa": upi_id,
            "pn": payee_name,
            "am": f"{amount.quantize(Decimal('0.01'))}",
            "cu": "INR",
            "tn": note[:50],
        }
    )
    return f"upi://pay?{query}"


def claim_note(student_code: str, installment_number: int) -> str:
    return f"NICT {student_code} Inst {installment_number}"


def claim_is_duplicate(
    db: Session, upi_reference: str, exclude_claim_id: int | None = None
) -> bool:
    query = select(PaymentClaim.id).where(
        PaymentClaim.upi_reference == upi_reference,
        PaymentClaim.status.in_((CLAIM_PENDING, CLAIM_APPROVED)),
    )
    if exclude_claim_id is not None:
        query = query.where(PaymentClaim.id != exclude_claim_id)
    return db.scalar(query) is not None


def claim_age_days(claim: PaymentClaim, today: date | None = None) -> int:
    submitted = claim.submitted_at.date() if claim.submitted_at else date.today()
    return max(((today or date.today()) - submitted).days, 0)
