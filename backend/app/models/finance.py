from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Expense(Base):
    """A branch expense used by the cash book, P&L and GST reports."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Cash"
    )
    vendor: Mapped[str | None] = mapped_column(String(150), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    branch: Mapped["Branch"] = relationship("Branch")
    recorded_by: Mapped["User | None"] = relationship("User")


class BankAccount(Base):
    """A bank account shown in the finance module.

    Accounts may belong to a branch or to head office (``branch_id`` null).
    """

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_name: Mapped[str] = mapped_column(String(150), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    branch: Mapped["Branch | None"] = relationship("Branch")


class FranchiseProfile(Base):
    """Agreement and royalty terms for a franchise branch."""

    __tablename__ = "franchise_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    owner_name: Mapped[str] = mapped_column(String(150), nullable=False)
    owner_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agreement_start: Mapped[date] = mapped_column(Date, nullable=False)
    agreement_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    royalty_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=10
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    branch: Mapped["Branch"] = relationship("Branch")
    royalty_payments: Mapped[list["RoyaltyPayment"]] = relationship(
        "RoyaltyPayment",
        back_populates="franchise",
        cascade="all, delete-orphan",
    )


class RoyaltyPayment(Base):
    """A royalty settlement recorded by head office."""

    __tablename__ = "royalty_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    franchise_id: Mapped[int] = mapped_column(
        ForeignKey("franchise_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    franchise: Mapped["FranchiseProfile"] = relationship(
        "FranchiseProfile", back_populates="royalty_payments"
    )
    recorded_by: Mapped["User | None"] = relationship("User")
