from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


FRANCHISE_STATUSES = ("active", "suspended", "terminated")


# ---------------------------------------------------------------------------
# Franchise profiles
# ---------------------------------------------------------------------------
class FranchiseCreate(BaseModel):
    branch_id: int
    owner_name: str = Field(min_length=2, max_length=150)
    owner_phone: str | None = Field(default=None, max_length=30)
    owner_email: EmailStr | None = None
    agreement_start: date
    agreement_end: date | None = None
    royalty_percent: Decimal = Field(default=Decimal("10"), ge=0, le=100)
    status: str = Field(default="active", max_length=20)
    notes: str | None = None


class FranchiseUpdate(BaseModel):
    owner_name: str | None = Field(default=None, min_length=2, max_length=150)
    owner_phone: str | None = Field(default=None, max_length=30)
    owner_email: EmailStr | None = None
    agreement_start: date | None = None
    agreement_end: date | None = None
    royalty_percent: Decimal | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, max_length=20)
    notes: str | None = None


class FranchiseResponse(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    branch_code: str
    owner_name: str
    owner_phone: str | None
    owner_email: str | None
    agreement_start: date
    agreement_end: date | None
    royalty_percent: Decimal
    status: str
    notes: str | None
    students: int
    revenue: Decimal
    royalty_paid: Decimal
    royalty_due: Decimal
    created_at: datetime


# ---------------------------------------------------------------------------
# Royalty settlements
# ---------------------------------------------------------------------------
class RoyaltyCreate(BaseModel):
    franchise_id: int
    amount: Decimal = Field(gt=0)
    payment_date: date
    period_from: date
    period_to: date
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class RoyaltyUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    payment_date: date | None = None
    period_from: date | None = None
    period_to: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class RoyaltyResponse(BaseModel):
    id: int
    franchise_id: int
    branch_name: str
    owner_name: str
    amount: Decimal
    payment_date: date
    period_from: date
    period_to: date
    reference: str | None
    notes: str | None
    recorded_by: str | None
    created_at: datetime


class FranchiseSummary(BaseModel):
    franchises: int
    active_franchises: int
    students: int
    revenue: Decimal
    royalty_expected: Decimal
    royalty_paid: Decimal
    royalty_due: Decimal
