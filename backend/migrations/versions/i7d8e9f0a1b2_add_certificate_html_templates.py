"""add safe HTML certificate templates

Revision ID: i7d8e9f0a1b2
Revises: h6c7d8e9f0a1
"""

from alembic import op
import sqlalchemy as sa

revision = "i7d8e9f0a1b2"
down_revision = "h6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("certificate_template", sa.Text(), nullable=True))
    op.add_column("branches", sa.Column("marksheet_template", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("branches", "marksheet_template")
    op.drop_column("branches", "certificate_template")
