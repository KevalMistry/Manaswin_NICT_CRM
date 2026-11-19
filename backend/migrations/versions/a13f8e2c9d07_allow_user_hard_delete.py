"""allow hard deletion of managed users

Revision ID: a13f8e2c9d07
Revises: 9c2e7d8a1f04
"""
from alembic import op
import sqlalchemy as sa

revision = "a13f8e2c9d07"
down_revision = "9c2e7d8a1f04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("attendance_ibfk_2", "attendance", type_="foreignkey")
    op.alter_column("attendance", "marked_by_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "attendance_marked_by_fk",
        "attendance",
        "users",
        ["marked_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("performance_reviews_ibfk_1", "performance_reviews", type_="foreignkey")
    op.drop_constraint("performance_reviews_ibfk_2", "performance_reviews", type_="foreignkey")
    op.alter_column("performance_reviews", "reviewed_by_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "performance_reviews_reviewed_by_fk",
        "performance_reviews",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "performance_reviews_user_fk",
        "performance_reviews",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("performance_reviews_reviewed_by_fk", "performance_reviews", type_="foreignkey")
    op.drop_constraint("performance_reviews_user_fk", "performance_reviews", type_="foreignkey")
    op.alter_column("performance_reviews", "reviewed_by_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("performance_reviews_ibfk_1", "performance_reviews", "users", ["reviewed_by_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("performance_reviews_ibfk_2", "performance_reviews", "users", ["user_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("attendance_marked_by_fk", "attendance", type_="foreignkey")
    op.alter_column("attendance", "marked_by_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("attendance_ibfk_2", "attendance", "users", ["marked_by_id"], ["id"], ondelete="RESTRICT")
