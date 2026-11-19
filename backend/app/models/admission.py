from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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


# Application lifecycle. ``approved`` is kept as an explicit state for records
# that were cleared by an administrator but whose enrollment could not be
# created in the same transaction; the normal approval path moves straight to
# ``enrolled``.
ADMISSION_STATUSES = (
    "submitted",
    "under_review",
    "approved",
    "rejected",
    "enrolled",
    "withdrawn",
)
ADMISSION_PAYMENT_STATUSES = ("unpaid", "pending", "paid", "refunded")


class AdmissionApplication(Base):
    __tablename__ = "admission_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)
    parent_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    parent_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="submitted", server_default="submitted"
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unpaid", server_default="unpaid"
    )
    registration_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="online", server_default="online"
    )

    # Random token that lets an applicant upload documents and track their own
    # application without creating an account. Never exposed in list endpoints.
    upload_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey("enrollments.id", ondelete="SET NULL"), unique=True, nullable=True
    )

    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    branch: Mapped["Branch"] = relationship("Branch")
    course: Mapped["Course"] = relationship("Course")
    batch: Mapped["Batch | None"] = relationship("Batch")
    student: Mapped["Student | None"] = relationship("Student")
    enrollment: Mapped["Enrollment | None"] = relationship("Enrollment")
    reviewed_by: Mapped["User | None"] = relationship("User")
    documents: Mapped[list["AdmissionDocument"]] = relationship(
        "AdmissionDocument",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list["AdmissionPayment"]] = relationship(
        "AdmissionPayment",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AdmissionDocument(Base):
    __tablename__ = "admission_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("admission_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Path relative to the private admission upload root. Files are never
    # served by the public /uploads media route; downloads require the
    # applicant token or staff authentication.
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    application: Mapped["AdmissionApplication"] = relationship(
        "AdmissionApplication", back_populates="documents"
    )


class AdmissionPayment(Base):
    __tablename__ = "admission_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("admission_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str | None] = mapped_column(
        String(40), unique=True, nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    gst_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    payment_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual", server_default="manual"
    )
    provider: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual", server_default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    application: Mapped["AdmissionApplication"] = relationship(
        "AdmissionApplication", back_populates="payments"
    )
    recorded_by: Mapped["User | None"] = relationship("User")
