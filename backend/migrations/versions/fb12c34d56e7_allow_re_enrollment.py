"""allow re-enrollment into the same batch

Revision ID: fb12c34d56e7
Revises: e1f2a3b4c5d6

A completed or cancelled enrollment is kept as history. The application already
blocks duplicate *active* enrollments, so the database-wide unique constraint is
removed to let a student rejoin the same batch later with a fresh enrollment.
"""
from alembic import op


revision = "fb12c34d56e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL reuses the composite unique index for the student_id foreign key,
    # so give that key its own index before removing the unique constraint.
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.drop_constraint(
        "uq_enrollment_student_batch", "enrollments", type_="unique"
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_enrollment_student_batch", "enrollments", ["student_id", "batch_id"]
    )
    op.drop_index("ix_enrollments_student_id", table_name="enrollments")
