"""add course application and examination fees

Revision ID: f4a5b6c7d8e9
Revises: b3c4d5e6f7a8
"""
from alembic import op
import sqlalchemy as sa


revision = "f4a5b6c7d8e9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("application_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "courses",
        sa.Column("exam_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("courses", "exam_fee")
    op.drop_column("courses", "application_fee")
