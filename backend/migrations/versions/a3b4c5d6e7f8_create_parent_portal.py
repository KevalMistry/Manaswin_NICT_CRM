"""create parent portal

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-29 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the Parent role and the parent-to-student link table."""
    op.execute(
        sa.text(
            "INSERT INTO roles (name, description, is_active) "
            "SELECT 'Parent', 'Read-only guardian portal access', 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Parent')"
        )
    )
    op.create_table(
        "parent_student_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "parent_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship",
            sa.String(length=40),
            nullable=False,
            server_default="Guardian",
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "parent_user_id", "student_id", name="uq_parent_student_link"
        ),
    )
    op.create_index(
        "ix_parent_student_links_parent_user_id",
        "parent_student_links",
        ["parent_user_id"],
    )
    op.create_index(
        "ix_parent_student_links_student_id",
        "parent_student_links",
        ["student_id"],
    )


def downgrade() -> None:
    """Remove the link table and the Parent role."""
    op.drop_table("parent_student_links")
    op.execute(sa.text("DELETE FROM roles WHERE name = 'Parent'"))
