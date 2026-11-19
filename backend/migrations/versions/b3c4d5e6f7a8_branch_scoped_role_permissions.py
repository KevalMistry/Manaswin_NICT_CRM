"""scope role module permissions by branch

Revision ID: b3c4d5e6f7a8
Revises: e8f9a0b1c2d3
"""
from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "role_module_permissions",
        sa.Column("branch_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_role_module_permissions_branch_id",
        "role_module_permissions",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_role_module_permission",
        "role_module_permissions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_role_module_permission_branch",
        "role_module_permissions",
        ["branch_id", "role_id", "module_key"],
    )
    op.create_index(
        "ix_role_module_permissions_branch_id",
        "role_module_permissions",
        ["branch_id"],
    )


def downgrade() -> None:
    # Branch overrides cannot fit the old (role_id, module_key) unique key.
    op.execute("DELETE FROM role_module_permissions WHERE branch_id IS NOT NULL")
    op.drop_index(
        "ix_role_module_permissions_branch_id",
        table_name="role_module_permissions",
    )
    op.drop_constraint(
        "uq_role_module_permission_branch",
        "role_module_permissions",
        type_="unique",
    )
    op.drop_constraint(
        "fk_role_module_permissions_branch_id",
        "role_module_permissions",
        type_="foreignkey",
    )
    op.drop_column("role_module_permissions", "branch_id")
    op.create_unique_constraint(
        "uq_role_module_permission",
        "role_module_permissions",
        ["role_id", "module_key"],
    )
