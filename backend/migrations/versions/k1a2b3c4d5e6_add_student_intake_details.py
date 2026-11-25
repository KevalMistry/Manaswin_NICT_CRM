"""add intake details to students

Revision ID: k1a2b3c4d5e6
Revises: j8e9f0a1b2c3
"""

from alembic import op
import sqlalchemy as sa

revision = "k1a2b3c4d5e6"
down_revision = "j8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("batch_time", sa.String(50), nullable=True))
    op.add_column("students", sa.Column("course_name", sa.String(150), nullable=True))
    op.add_column(
        "students", sa.Column("registration_number", sa.String(50), nullable=True)
    )
    op.add_column("students", sa.Column("form_number", sa.String(50), nullable=True))
    op.add_column("students", sa.Column("date_of_joining", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "date_of_joining")
    op.drop_column("students", "form_number")
    op.drop_column("students", "registration_number")
    op.drop_column("students", "course_name")
    op.drop_column("students", "batch_time")
