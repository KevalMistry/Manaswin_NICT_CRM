from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id",
            "document_type",
            name="uq_certificate_enrollment_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    certificate_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    verification_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(5), nullable=True)
    percentage: Mapped[float | None] = mapped_column(nullable=True)
    digital_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_valid: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    enrollment: Mapped["Enrollment"] = relationship("Enrollment")
