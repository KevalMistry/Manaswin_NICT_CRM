from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # UPI collection details used by the student portal. Optional so branches
    # that collect fees only at the counter keep working unchanged.
    upi_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upi_payee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upi_qr_code_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    marksheet_title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    certificate_primary_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#172a43", server_default="#172a43"
    )
    certificate_accent_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#c19a3d", server_default="#c19a3d"
    )
    certificate_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    marksheet_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Geofence used to verify staff self check-in. Coordinates are optional so
    # existing branches keep working, but self check-in is refused until an
    # administrator configures them.
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geofence_radius_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=150, server_default="150"
    )
    # Optional office network allowlist (comma-separated IPv4/IPv6 addresses
    # or CIDR ranges). Empty means "do not check the network".
    office_network: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="branch",
        passive_deletes=True,
    )
    students: Mapped[list["Student"]] = relationship(
        "Student",
        back_populates="branch",
        passive_deletes=True,
    )
