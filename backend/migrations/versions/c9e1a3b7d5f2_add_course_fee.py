"""add course fee amount

Revision ID: c9e1a3b7d5f2
Revises: a7c9e1f4b2d6

Stores the standard fee for a course so an enrollment's fee plan can be
pre-filled instead of retyped. Existing courses are backfilled from the gross
total of their current fee plans, when one exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1a3b7d5f2"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f4b2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("fee_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    # Backfill only empty values, using the highest existing gross fee plan for
    # the course. Operational fee plans are left untouched.
    op.execute(
        """
        UPDATE courses c
        JOIN (
            SELECT b.course_id, MAX(fp.total_amount) AS course_fee
            FROM fee_plans fp
            JOIN enrollments e ON e.id = fp.enrollment_id
            JOIN batches b ON b.id = e.batch_id
            GROUP BY b.course_id
        ) existing ON existing.course_id = c.id
        SET c.fee_amount = existing.course_fee
        WHERE c.fee_amount IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("courses", "fee_amount")
