"""add certificate design settings

Revision ID: h6c7d8e9f0a1
Revises: g5b6c7d8e9f0
"""

from alembic import op
import sqlalchemy as sa

revision = "h6c7d8e9f0a1"
down_revision = "g5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("certificate_title", sa.String(length=180), nullable=True))
    op.add_column("branches", sa.Column("marksheet_title", sa.String(length=180), nullable=True))
    op.add_column(
        "branches",
        sa.Column("certificate_primary_color", sa.String(length=7), nullable=False, server_default="#172a43"),
    )
    op.add_column(
        "branches",
        sa.Column("certificate_accent_color", sa.String(length=7), nullable=False, server_default="#c19a3d"),
    )


def downgrade() -> None:
    op.drop_column("branches", "certificate_accent_color")
    op.drop_column("branches", "certificate_primary_color")
    op.drop_column("branches", "marksheet_title")
    op.drop_column("branches", "certificate_title")
