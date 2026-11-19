"""add student UPI payment claims and editable email templates

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
Create Date: 2026-10-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("upi_id", sa.String(length=120), nullable=True))
    op.add_column(
        "branches", sa.Column("upi_payee_name", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "notification_logs",
        sa.Column("template_key", sa.String(length=60), nullable=True),
    )

    op.create_table(
        "payment_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "installment_id",
            sa.Integer(),
            sa.ForeignKey("fee_installments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("upi_reference", sa.String(length=60), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "submitted_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "reviewed_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_code", sa.String(length=30), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("staff_note", sa.String(length=255), nullable=True),
        sa.Column(
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("receipt_email_status", sa.String(length=20), nullable=True),
        sa.Column("receipt_email_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint("payment_id", name="uq_payment_claim_payment"),
    )
    op.create_index(
        "ix_payment_claims_installment_id", "payment_claims", ["installment_id"]
    )
    op.create_index(
        "ix_payment_claims_student_id", "payment_claims", ["student_id"]
    )
    op.create_index("ix_payment_claims_branch_id", "payment_claims", ["branch_id"])
    op.create_index("ix_payment_claims_status", "payment_claims", ["status"])
    op.create_index(
        "ix_payment_claims_upi_reference", "payment_claims", ["upi_reference"]
    )

    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_key", sa.String(length=60), nullable=False),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject_template", sa.String(length=255), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "updated_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint(
            "template_key", "branch_id", name="uq_email_template_scope"
        ),
    )
    op.create_index("ix_email_templates_template_key", "email_templates", ["template_key"])
    op.create_index("ix_email_templates_branch_id", "email_templates", ["branch_id"])


def downgrade() -> None:
    op.drop_table("email_templates")
    op.drop_table("payment_claims")
    op.drop_column("notification_logs", "template_key")
    op.drop_column("branches", "upi_payee_name")
    op.drop_column("branches", "upi_id")
