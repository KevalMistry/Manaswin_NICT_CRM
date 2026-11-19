"""create enquiries (CRM pipeline)

Revision ID: a7c9e1f4b2d6
Revises: fb12c34d56e7

Adds the CRM enquiry pipeline required by the specification
(New Lead -> Follow Up -> Demo -> Counselling -> Admission) and grants the
new module to the roles that work on admissions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9e1f4b2d6"
down_revision: Union[str, Sequence[str], None] = "fb12c34d56e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enquiries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enquiry_code", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("counsellor_id", sa.Integer(), nullable=True),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["counsellor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enquiry_code"),
    )
    op.create_index("ix_enquiries_branch_id", "enquiries", ["branch_id"])
    op.create_index("ix_enquiries_status", "enquiries", ["status"])
    op.create_index("ix_enquiries_follow_up_date", "enquiries", ["follow_up_date"])
    op.create_index("ix_enquiries_counsellor_id", "enquiries", ["counsellor_id"])
    op.create_index("ix_enquiries_student_id", "enquiries", ["student_id"])

    op.execute(
        """
        INSERT INTO role_module_permissions (role_id, module_key, can_access)
        SELECT r.id, 'enquiries',
               CASE WHEN r.name IN ('Super Admin', 'Branch Admin', 'Counsellor')
                    THEN 1 ELSE 0 END
        FROM roles r
        WHERE NOT EXISTS (
            SELECT 1 FROM role_module_permissions p
            WHERE p.role_id = r.id AND p.module_key = 'enquiries'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_module_permissions WHERE module_key = 'enquiries'"
    )
    op.drop_index("ix_enquiries_student_id", table_name="enquiries")
    op.drop_index("ix_enquiries_counsellor_id", table_name="enquiries")
    op.drop_index("ix_enquiries_follow_up_date", table_name="enquiries")
    op.drop_index("ix_enquiries_status", table_name="enquiries")
    op.drop_index("ix_enquiries_branch_id", table_name="enquiries")
    op.drop_table("enquiries")
