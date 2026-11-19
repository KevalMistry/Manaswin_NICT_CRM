from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    branch: Mapped["Branch | None"] = relationship(
        "Branch",
        back_populates="users",
    )

    @property
    def role_name(self) -> str:
        return self.role.name if self.role else "User"

    @property
    def allowed_modules(self) -> list[str]:
        """Return module keys this account may use in its branch.

        Permission rows are layered: built-in role defaults, optional global
        overrides, then overrides for this user's branch. This mirrors
        ``has_module_access`` so navigation and API access agree.
        """
        if not self.role:
            return []
        from app.services.permissions import merge_permission_rows

        rows = list(getattr(self.role, "module_permissions", []) or [])
        effective = merge_permission_rows(self.role.name, rows, self.branch_id)
        return [key for key, allowed in effective.items() if allowed]
