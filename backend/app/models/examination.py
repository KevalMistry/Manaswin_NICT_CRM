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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Examination(Base):
    __tablename__ = "examinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False
    )
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    batch: Mapped["Batch"] = relationship("Batch")
    subjects: Mapped[list["ExamSubject"]] = relationship(
        "ExamSubject", back_populates="examination", cascade="all, delete-orphan"
    )


class ExamSubject(Base):
    __tablename__ = "exam_subjects"
    __table_args__ = (
        UniqueConstraint("examination_id", "name", name="uq_exam_subject_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("examinations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    pass_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    examination: Mapped["Examination"] = relationship(
        "Examination", back_populates="subjects"
    )
    marks: Mapped[list["ExamMark"]] = relationship(
        "ExamMark", back_populates="subject", cascade="all, delete-orphan"
    )


class ExamMark(Base):
    __tablename__ = "exam_marks"
    __table_args__ = (
        UniqueConstraint(
            "exam_subject_id",
            "enrollment_id",
            name="uq_exam_mark_subject_enrollment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_subject_id: Mapped[int] = mapped_column(
        ForeignKey("exam_subjects.id", ondelete="CASCADE"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    marks_obtained: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(5), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    subject: Mapped["ExamSubject"] = relationship("ExamSubject", back_populates="marks")
    enrollment: Mapped["Enrollment"] = relationship("Enrollment")
