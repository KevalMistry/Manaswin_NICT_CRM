"""add branch geofence and staff attendance location proof

Revision ID: b7e2f9a4c6d1
Revises: 3fd701b16a5c
Create Date: 2026-10-29 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2f9a4c6d1"
down_revision: Union[str, Sequence[str], None] = "3fd701b16a5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add geofence configuration and location proof columns."""
    op.add_column(
        "branches",
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "branches",
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "branches",
        sa.Column(
            "geofence_radius_meters",
            sa.Integer(),
            server_default="150",
            nullable=False,
        ),
    )
    op.add_column(
        "branches",
        sa.Column("office_network", sa.String(length=255), nullable=True),
    )

    op.add_column(
        "staff_attendance",
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "staff_attendance",
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "staff_attendance",
        sa.Column("distance_meters", sa.Numeric(precision=9, scale=2), nullable=True),
    )
    op.add_column(
        "staff_attendance",
        sa.Column("location_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "staff_attendance",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove geofence configuration and location proof columns."""
    op.drop_column("staff_attendance", "ip_address")
    op.drop_column("staff_attendance", "location_status")
    op.drop_column("staff_attendance", "distance_meters")
    op.drop_column("staff_attendance", "longitude")
    op.drop_column("staff_attendance", "latitude")

    op.drop_column("branches", "office_network")
    op.drop_column("branches", "geofence_radius_meters")
    op.drop_column("branches", "longitude")
    op.drop_column("branches", "latitude")
