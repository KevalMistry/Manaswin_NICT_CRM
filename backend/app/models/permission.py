from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RoleModulePermission(Base):
    __tablename__ = "role_module_permissions"
    __table_args__ = (
        UniqueConstraint(
            "branch_id",
            "role_id",
            "module_key",
            name="uq_role_module_permission_branch",
        ),
        Index("ix_role_module_permissions_branch_id", "branch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    module_key: Mapped[str] = mapped_column(String(50), nullable=False)
    can_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    role: Mapped["Role"] = relationship("Role", back_populates="module_permissions")
