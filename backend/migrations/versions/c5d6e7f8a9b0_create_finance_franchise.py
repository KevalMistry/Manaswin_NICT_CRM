"""create finance and franchise tables

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create expenses, bank accounts, franchise profiles and royalties."""
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "gst_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "payment_method",
            sa.String(length=30),
            nullable=False,
            server_default="Cash",
        ),
        sa.Column("vendor", sa.String(length=150), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.String(length=500), nullable=True),
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
    )
    op.create_index("ix_expenses_branch_id", "expenses", ["branch_id"])
    op.create_index("ix_expenses_expense_date", "expenses", ["expense_date"])

    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("account_name", sa.String(length=150), nullable=False),
        sa.Column("bank_name", sa.String(length=150), nullable=False),
        sa.Column("account_number", sa.String(length=40), nullable=True),
        sa.Column("ifsc", sa.String(length=20), nullable=True),
        sa.Column(
            "opening_balance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_bank_accounts_branch_id", "bank_accounts", ["branch_id"])

    op.create_table(
        "franchise_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_name", sa.String(length=150), nullable=False),
        sa.Column("owner_phone", sa.String(length=30), nullable=True),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("agreement_start", sa.Date(), nullable=False),
        sa.Column("agreement_end", sa.Date(), nullable=True),
        sa.Column(
            "royalty_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint("branch_id", name="uq_franchise_profiles_branch"),
    )
    op.create_index(
        "ix_franchise_profiles_branch_id", "franchise_profiles", ["branch_id"]
    )

    op.create_table(
        "royalty_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "franchise_id",
            sa.Integer(),
            sa.ForeignKey("franchise_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_royalty_payments_franchise_id", "royalty_payments", ["franchise_id"]
    )


def downgrade() -> None:
    """Drop finance and franchise tables in dependency order."""
    op.drop_table("royalty_payments")
    op.drop_table("franchise_profiles")
    op.drop_table("bank_accounts")
    op.drop_table("expenses")
