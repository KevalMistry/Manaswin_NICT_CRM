import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.dependencies import DatabaseSession, require_roles
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogResponse


router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])
AuditReader = require_roles("Super Admin")


def record_audit(
    db: DatabaseSession,
    actor_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=json.dumps(details, separators=(",", ":")) if details else None,
    ))


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    db: DatabaseSession,
    _: User = Depends(AuditReader),
    action: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    return list(db.scalars(query).all())
