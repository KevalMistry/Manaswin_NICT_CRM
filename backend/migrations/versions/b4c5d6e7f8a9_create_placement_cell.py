"""create placement cell

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-29 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create companies, job openings, course eligibility and applications."""
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=150), nullable=True),
        sa.Column("contact_person", sa.String(length=150), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint("name", name="uq_companies_name"),
    )
    op.create_table(
        "job_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=150), nullable=True),
        sa.Column(
            "employment_type",
            sa.String(length=30),
            nullable=False,
            server_default="Full-time",
        ),
        sa.Column(
            "work_mode",
            sa.String(length=20),
            nullable=False,
            server_default="On-site",
        ),
        sa.Column("salary_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("salary_max", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "vacancies", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("last_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="open"
        ),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "ix_job_openings_company_id", "job_openings", ["company_id"]
    )
    op.create_index(
        "ix_job_openings_branch_id", "job_openings", ["branch_id"]
    )
    op.create_table(
        "job_opening_courses",
        sa.Column(
            "job_opening_id",
            sa.Integer(),
            sa.ForeignKey("job_openings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "placement_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_opening_id",
            sa.Integer(),
            sa.ForeignKey("job_openings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="applied",
        ),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="student",
        ),
        sa.Column("resume_url", sa.String(length=500), nullable=True),
        sa.Column("cover_note", sa.Text(), nullable=True),
        sa.Column("interview_date", sa.DateTime(), nullable=True),
        sa.Column("interview_mode", sa.String(length=30), nullable=True),
        sa.Column("interview_location", sa.String(length=255), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("offer_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("offer_date", sa.Date(), nullable=True),
        sa.Column("joining_date", sa.Date(), nullable=True),
        sa.Column("offer_letter_url", sa.String(length=500), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "job_opening_id", "student_id", name="uq_placement_application"
        ),
    )
    op.create_index(
        "ix_placement_applications_job_opening_id",
        "placement_applications",
        ["job_opening_id"],
    )
    op.create_index(
        "ix_placement_applications_student_id",
        "placement_applications",
        ["student_id"],
    )


def downgrade() -> None:
    """Drop the placement tables in dependency order."""
    op.drop_table("placement_applications")
    op.drop_table("job_opening_courses")
    op.drop_table("job_openings")
    op.drop_table("companies")
