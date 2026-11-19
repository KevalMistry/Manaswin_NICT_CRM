"""create online admission and registration payment tables

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add admission metadata columns and create admission tables."""
    op.add_column(
        "courses",
        sa.Column(
            "registration_fee",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "students",
        sa.Column("roll_number", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_students_roll_number", "students", ["roll_number"], unique=True
    )
    op.add_column(
        "branches",
        sa.Column("gstin", sa.String(length=20), nullable=True),
    )

    op.create_table(
        "admission_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_code", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=30), nullable=True),
        sa.Column("parent_name", sa.String(length=150), nullable=True),
        sa.Column("parent_phone", sa.String(length=30), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("qualification", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="submitted",
        ),
        sa.Column(
            "payment_status",
            sa.String(length=20),
            nullable=False,
            server_default="unpaid",
        ),
        sa.Column(
            "registration_fee",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default="online",
        ),
        sa.Column("upload_token", sa.String(length=64), nullable=False),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "enrollment_id",
            sa.Integer(),
            sa.ForeignKey("enrollments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint("application_code", name="uq_admission_application_code"),
        sa.UniqueConstraint("upload_token", name="uq_admission_upload_token"),
        sa.UniqueConstraint("student_id", name="uq_admission_student"),
        sa.UniqueConstraint("enrollment_id", name="uq_admission_enrollment"),
    )
    op.create_index(
        "ix_admission_applications_branch_id",
        "admission_applications",
        ["branch_id"],
    )
    op.create_index(
        "ix_admission_applications_course_id",
        "admission_applications",
        ["course_id"],
    )
    op.create_index(
        "ix_admission_applications_status",
        "admission_applications",
        ["status"],
    )
    op.create_index(
        "ix_admission_applications_payment_status",
        "admission_applications",
        ["payment_status"],
    )

    op.create_table(
        "admission_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("admission_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "uploaded_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "ix_admission_documents_application_id",
        "admission_documents",
        ["application_id"],
    )

    op.create_table(
        "admission_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("admission_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(length=40), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "taxable_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "gst_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "payment_method",
            sa.String(length=30),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("provider_order_id", sa.String(length=100), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=100), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column(
            "recorded_by_id",
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
        sa.UniqueConstraint("invoice_number", name="uq_admission_invoice_number"),
    )
    op.create_index(
        "ix_admission_payments_application_id",
        "admission_payments",
        ["application_id"],
    )
    op.create_index(
        "ix_admission_payments_status", "admission_payments", ["status"]
    )


def downgrade() -> None:
    """Drop admission tables and the added metadata columns."""
    op.drop_index("ix_admission_payments_status", table_name="admission_payments")
    op.drop_index(
        "ix_admission_payments_application_id", table_name="admission_payments"
    )
    op.drop_table("admission_payments")

    op.drop_index(
        "ix_admission_documents_application_id", table_name="admission_documents"
    )
    op.drop_table("admission_documents")

    op.drop_index(
        "ix_admission_applications_payment_status",
        table_name="admission_applications",
    )
    op.drop_index(
        "ix_admission_applications_status", table_name="admission_applications"
    )
    op.drop_index(
        "ix_admission_applications_course_id", table_name="admission_applications"
    )
    op.drop_index(
        "ix_admission_applications_branch_id", table_name="admission_applications"
    )
    op.drop_table("admission_applications")

    op.drop_column("branches", "gstin")
    op.drop_index("ix_students_roll_number", table_name="students")
    op.drop_column("students", "roll_number")
    op.drop_column("courses", "registration_fee")
