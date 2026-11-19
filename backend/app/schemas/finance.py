from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


EXPENSE_CATEGORIES = (
    "Rent",
    "Salaries",
    "Utilities",
    "Marketing",
    "Maintenance",
    "Teaching Material",
    "Software",
    "Travel",
    "Royalty",
    "Miscellaneous",
)

PAYMENT_METHODS = ("Cash", "UPI", "Bank Transfer", "Cheque", "Card", "Other")


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
class ExpenseCreate(BaseModel):
    branch_id: int | None = None
    category: str = Field(min_length=2, max_length=40)
    description: str = Field(min_length=2, max_length=255)
    amount: Decimal = Field(gt=0)
    gst_amount: Decimal = Field(default=Decimal("0"), ge=0)
    expense_date: date
    payment_method: str = Field(default="Cash", max_length=30)
    vendor: str | None = Field(default=None, max_length=150)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    receipt_url: str | None = Field(default=None, max_length=500)


class ExpenseUpdate(BaseModel):
    branch_id: int | None = None
    category: str | None = Field(default=None, min_length=2, max_length=40)
    description: str | None = Field(default=None, min_length=2, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    gst_amount: Decimal | None = Field(default=None, ge=0)
    expense_date: date | None = None
    payment_method: str | None = Field(default=None, max_length=30)
    vendor: str | None = Field(default=None, max_length=150)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    receipt_url: str | None = Field(default=None, max_length=500)


class ExpenseResponse(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    category: str
    description: str
    amount: Decimal
    gst_amount: Decimal
    expense_date: date
    payment_method: str
    vendor: str | None
    reference: str | None
    notes: str | None
    receipt_url: str | None
    recorded_by: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Bank accounts
# ---------------------------------------------------------------------------
class BankAccountCreate(BaseModel):
    branch_id: int | None = None
    account_name: str = Field(min_length=2, max_length=150)
    bank_name: str = Field(min_length=2, max_length=150)
    account_number: str | None = Field(default=None, max_length=40)
    ifsc: str | None = Field(default=None, max_length=20)
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True


class BankAccountUpdate(BaseModel):
    branch_id: int | None = None
    account_name: str | None = Field(default=None, min_length=2, max_length=150)
    bank_name: str | None = Field(default=None, min_length=2, max_length=150)
    account_number: str | None = Field(default=None, max_length=40)
    ifsc: str | None = Field(default=None, max_length=20)
    opening_balance: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class BankAccountResponse(BaseModel):
    id: int
    branch_id: int | None
    branch_name: str | None
    account_name: str
    bank_name: str
    account_number: str | None
    ifsc: str | None
    opening_balance: Decimal
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Summary and cash book
# ---------------------------------------------------------------------------
class FinanceSummary(BaseModel):
    fees_collected: Decimal
    expenses: Decimal
    net_income: Decimal
    outstanding_fees: Decimal
    gst_payable: Decimal
    gst_rate_percent: float
    bank_balance: Decimal
    active_bank_accounts: int
    expense_count: int


class CashBookEntry(BaseModel):
    entry_date: date
    entry_type: str
    reference: str
    description: str
    category: str | None
    branch_name: str
    money_in: Decimal
    money_out: Decimal


class CashBookResponse(BaseModel):
    opening_balance: Decimal
    closing_balance: Decimal
    total_in: Decimal
    total_out: Decimal
    entries: list[CashBookEntry]
