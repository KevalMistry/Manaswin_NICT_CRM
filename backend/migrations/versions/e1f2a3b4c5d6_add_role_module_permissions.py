"""add database controlled role module permissions

Revision ID: e1f2a3b4c5d6
Revises: d84e7f1a2b03
"""
from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d84e7f1a2b03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_module_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=50), nullable=False),
        sa.Column("can_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("role_id", "module_key", name="uq_role_module_permission"),
    )
    op.create_index("ix_role_module_permissions_role_id", "role_module_permissions", ["role_id"])


def downgrade() -> None:
    op.drop_index("ix_role_module_permissions_role_id", table_name="role_module_permissions")
    op.drop_table("role_module_permissions")
