from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class QuestionBank(Base):
    """A reusable set of questions for a course."""

    __tablename__ = "question_banks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional published Google/Microsoft Forms link. When set, a bank can be
    # reused as the source of an external-form exam without typing questions.
    external_form_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_form_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    course: Mapped["Course"] = relationship("Course")
    questions: Mapped[list["BankQuestion"]] = relationship(
        "BankQuestion",
        back_populates="bank",
        cascade="all, delete-orphan",
        order_by="BankQuestion.position",
    )


class BankQuestion(Base):
    """A single multiple-choice question stored in a question bank."""

    __tablename__ = "bank_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(String(300), nullable=False)
    option_b: Mapped[str] = mapped_column(String(300), nullable=False)
    option_c: Mapped[str] = mapped_column(String(300), nullable=False)
    option_d: Mapped[str] = mapped_column(String(300), nullable=False)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=1)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    bank: Mapped["QuestionBank"] = relationship("QuestionBank", back_populates="questions")


class OnlineExam(Base):
    """A timed, auto-graded online examination for a course."""

    __tablename__ = "online_exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Published Google/Microsoft Forms link used instead of in-CRM questions.
    external_form_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_form_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    pass_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    negative_marking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    results_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    course: Mapped["Course"] = relationship("Course")
    batch: Mapped["Batch | None"] = relationship("Batch")
    questions: Mapped[list["ExamQuestion"]] = relationship(
        "ExamQuestion",
        back_populates="exam",
        cascade="all, delete-orphan",
        order_by="ExamQuestion.position",
    )
    attempts: Mapped[list["ExamAttempt"]] = relationship(
        "ExamAttempt",
        back_populates="exam",
        cascade="all, delete-orphan",
    )


class ExamQuestion(Base):
    """A question snapshot copied into an exam.

    Questions are copied rather than referenced so that later edits to the
    question bank cannot change an exam that students have already attempted.
    """

    __tablename__ = "exam_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("online_exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_questions.id", ondelete="SET NULL"), nullable=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(String(300), nullable=False)
    option_b: Mapped[str] = mapped_column(String(300), nullable=False)
    option_c: Mapped[str] = mapped_column(String(300), nullable=False)
    option_d: Mapped[str] = mapped_column(String(300), nullable=False)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=1)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    exam: Mapped["OnlineExam"] = relationship("OnlineExam", back_populates="questions")


class ExamAttempt(Base):
    """One timed sitting of an exam by a student."""

    __tablename__ = "exam_attempts"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "enrollment_id",
            "attempt_number",
            name="uq_exam_attempt_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("online_exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    # Comma-separated exam question ids in the order shown to the student.
    question_order: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    total_marks: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    percentage: Mapped[float] = mapped_column(nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    exam: Mapped["OnlineExam"] = relationship("OnlineExam", back_populates="attempts")
    enrollment: Mapped["Enrollment"] = relationship("Enrollment")
    answers: Mapped[list["ExamAnswer"]] = relationship(
        "ExamAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class ExamAnswer(Base):
    """A student's saved answer to one exam question."""

    __tablename__ = "exam_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_exam_answer_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("exam_questions.id", ondelete="CASCADE"), nullable=False
    )
    selected_option: Mapped[str | None] = mapped_column(String(1), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marks_awarded: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=0
    )

    attempt: Mapped["ExamAttempt"] = relationship("ExamAttempt", back_populates="answers")
