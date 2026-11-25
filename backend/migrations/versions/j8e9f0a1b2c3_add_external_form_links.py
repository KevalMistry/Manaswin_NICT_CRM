"""add published external form links to banks and exams

Revision ID: j8e9f0a1b2c3
Revises: i7d8e9f0a1b2
"""

from alembic import op
import sqlalchemy as sa

revision = "j8e9f0a1b2c3"
down_revision = "i7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "question_banks", sa.Column("external_form_url", sa.String(1000), nullable=True)
    )
    op.add_column(
        "question_banks",
        sa.Column("external_form_provider", sa.String(20), nullable=True),
    )
    op.add_column(
        "online_exams", sa.Column("external_form_url", sa.String(1000), nullable=True)
    )
    op.add_column(
        "online_exams",
        sa.Column("external_form_provider", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("online_exams", "external_form_provider")
    op.drop_column("online_exams", "external_form_url")
    op.drop_column("question_banks", "external_form_provider")
    op.drop_column("question_banks", "external_form_url")
