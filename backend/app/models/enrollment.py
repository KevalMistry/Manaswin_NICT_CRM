from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False
    )
    admission_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    student: Mapped["Student"] = relationship("Student")
    batch: Mapped["Batch"] = relationship("Batch")
    fee_plan: Mapped["FeePlan | None"] = relationship(
        "FeePlan", back_populates="enrollment", uselist=False, passive_deletes=True
    )

    @property
    def course_end_date(self) -> date | None:
        """When this enrollment's course is scheduled to finish."""
        from app.services.course_lifecycle import enrollment_course_end_date

        return enrollment_course_end_date(self)

    @property
    def days_remaining(self) -> int | None:
        """Days until the course ends; negative after the end date."""
        from app.services.course_lifecycle import enrollment_course_timing

        _, remaining, _ = enrollment_course_timing(self)
        return remaining
