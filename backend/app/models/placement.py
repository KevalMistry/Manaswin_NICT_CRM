from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


job_opening_courses = Table(
    "job_opening_courses",
    Base.metadata,
    Column(
        "job_opening_id",
        ForeignKey("job_openings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "course_id",
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Company(Base):
    """A hiring partner in the placement cell's company database."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    openings: Mapped[list["JobOpening"]] = relationship(
        "JobOpening", back_populates="company"
    )


class JobOpening(Base):
    """A live vacancy shared with eligible students.

    ``branch_id`` is null for openings available to every branch. Course links
    restrict eligibility; an opening with no course links is open to all
    courses.
    """

    __tablename__ = "job_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    employment_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Full-time"
    )
    work_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="On-site"
    )
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vacancies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="openings")
    branch: Mapped["Branch | None"] = relationship("Branch")
    courses: Mapped[list["Course"]] = relationship(
        "Course", secondary=job_opening_courses
    )
    applications: Mapped[list["PlacementApplication"]] = relationship(
        "PlacementApplication", back_populates="opening"
    )


class PlacementApplication(Base):
    """One student's progress through the placement pipeline.

    Interview scheduling, feedback, offer details and the offer-letter link all
    live here so the placement office has a single record per student/opening.
    """

    __tablename__ = "placement_applications"
    __table_args__ = (
        UniqueConstraint(
            "job_opening_id", "student_id", name="uq_placement_application"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_opening_id: Mapped[int] = mapped_column(
        ForeignKey("job_openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="applied"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="student"
    )
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interview_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    interview_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_letter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    opening: Mapped["JobOpening"] = relationship(
        "JobOpening", back_populates="applications"
    )
    student: Mapped["Student"] = relationship("Student")
