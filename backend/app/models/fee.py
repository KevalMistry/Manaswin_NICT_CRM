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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FeePlan(Base):
    __tablename__ = "fee_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    scholarship_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="fee_plan")
    installments: Mapped[list["FeeInstallment"]] = relationship(
        "FeeInstallment", back_populates="fee_plan", cascade="all, delete-orphan"
    )


class FeeInstallment(Base):
    __tablename__ = "fee_installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fee_plan_id: Mapped[int] = mapped_column(
        ForeignKey("fee_plans.id", ondelete="CASCADE"), nullable=False
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    fee_plan: Mapped["FeePlan"] = relationship("FeePlan", back_populates="installments")
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="installment", passive_deletes=True
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    installment_id: Mapped[int] = mapped_column(
        ForeignKey("fee_installments.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    installment: Mapped["FeeInstallment"] = relationship(
        "FeeInstallment", back_populates="payments"
    )


class PaymentClaim(Base):
    """A student's self-reported UPI transfer awaiting staff verification.

    Claims are deliberately kept separate from ``Payment`` rows so a pending or
    rejected claim can never change a fee balance or appear in reports. A
    normal ``Payment`` is created only when staff confirm the bank credit.
    """

    __tablename__ = "payment_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installment_id: Mapped[int] = mapped_column(
        ForeignKey("fee_installments.id", ondelete="RESTRICT"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    upi_reference: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    staff_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    receipt_email_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    receipt_email_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    installment: Mapped["FeeInstallment"] = relationship("FeeInstallment")
    student: Mapped["Student"] = relationship("Student")
    branch: Mapped["Branch"] = relationship("Branch")
    reviewed_by: Mapped["User | None"] = relationship("User")
    payment: Mapped["Payment | None"] = relationship("Payment")


class EmailTemplate(Base):
    """Editable outbound email copy, optionally overridden per branch."""

    __tablename__ = "email_templates"
    __table_args__ = (
        # branch_id NULL is the global default. MySQL cannot enforce uniqueness
        # across NULLs, so the API also checks for an existing global row.
        UniqueConstraint(
            "template_key", "branch_id", name="uq_email_template_scope"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_template: Mapped[str] = mapped_column(String(255), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    branch: Mapped["Branch | None"] = relationship("Branch")
    updated_by: Mapped["User | None"] = relationship("User")
