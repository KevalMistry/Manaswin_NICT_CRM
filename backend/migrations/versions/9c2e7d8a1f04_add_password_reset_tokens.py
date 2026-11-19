"""add password reset tokens

Revision ID: 9c2e7d8a1f04
Revises: 06163150ddf4
"""
from alembic import op
import sqlalchemy as sa

revision = "9c2e7d8a1f04"
down_revision = "06163150ddf4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
