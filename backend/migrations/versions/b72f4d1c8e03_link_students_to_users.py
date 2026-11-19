"""link students to user accounts

Revision ID: b72f4d1c8e03
Revises: a13f8e2c9d07
"""
from alembic import op
import sqlalchemy as sa


revision = "b72f4d1c8e03"
down_revision = "a13f8e2c9d07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_students_user_id", "students", ["user_id"])
    op.create_foreign_key(
        "students_user_fk",
        "students",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("students_user_fk", "students", type_="foreignkey")
    op.drop_constraint("uq_students_user_id", "students", type_="unique")
    op.drop_column("students", "user_id")
