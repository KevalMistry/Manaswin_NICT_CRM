"""create online exam engine tables

Revision ID: d9e2f3a4b5c6
Revises: c8f1a2d3e4b5
Create Date: 2026-10-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c8f1a2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the question bank and timed online exam tables."""
    op.create_table(
        "question_banks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_question_banks_course_id", "question_banks", ["course_id"])

    op.create_table(
        "bank_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bank_id",
            sa.Integer(),
            sa.ForeignKey("question_banks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_a", sa.String(length=300), nullable=False),
        sa.Column("option_b", sa.String(length=300), nullable=False),
        sa.Column("option_c", sa.String(length=300), nullable=False),
        sa.Column("option_d", sa.String(length=300), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("marks", sa.Numeric(6, 2), nullable=False, server_default="1"),
        sa.Column("difficulty", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_bank_questions_bank_id", "bank_questions", ["bank_id"])

    op.create_table(
        "online_exams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("pass_percentage", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "negative_marking", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "results_published", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_online_exams_course_id", "online_exams", ["course_id"])
    op.create_index("ix_online_exams_batch_id", "online_exams", ["batch_id"])

    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exam_id",
            sa.Integer(),
            sa.ForeignKey("online_exams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_question_id",
            sa.Integer(),
            sa.ForeignKey("bank_questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_a", sa.String(length=300), nullable=False),
        sa.Column("option_b", sa.String(length=300), nullable=False),
        sa.Column("option_c", sa.String(length=300), nullable=False),
        sa.Column("option_d", sa.String(length=300), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("marks", sa.Numeric(6, 2), nullable=False, server_default="1"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_exam_questions_exam_id", "exam_questions", ["exam_id"])

    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exam_id",
            sa.Integer(),
            sa.ForeignKey("online_exams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            sa.Integer(),
            sa.ForeignKey("enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
        sa.Column("question_order", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("score", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("total_marks", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "auto_submitted", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.UniqueConstraint(
            "exam_id",
            "enrollment_id",
            "attempt_number",
            name="uq_exam_attempt_number",
        ),
    )
    op.create_index("ix_exam_attempts_exam_id", "exam_attempts", ["exam_id"])
    op.create_index("ix_exam_attempts_enrollment_id", "exam_attempts", ["enrollment_id"])

    op.create_table(
        "exam_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("exam_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("selected_option", sa.String(length=1), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "marks_awarded", sa.Numeric(6, 2), nullable=False, server_default="0"
        ),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_exam_answer_question"),
    )
    op.create_index("ix_exam_answers_attempt_id", "exam_answers", ["attempt_id"])


def downgrade() -> None:
    """Drop the online exam engine tables."""
    op.drop_table("exam_answers")
    op.drop_table("exam_attempts")
    op.drop_table("exam_questions")
    op.drop_table("online_exams")
    op.drop_table("bank_questions")
    op.drop_table("question_banks")
