"""add branch UPI QR code

Revision ID: g5b6c7d8e9f0
Revises: f4a5b6c7d8e9
"""

from alembic import op
import sqlalchemy as sa


revision = "g5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branches",
        sa.Column("upi_qr_code_url", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branches", "upi_qr_code_url")
