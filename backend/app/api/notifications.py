from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    require_module,
    require_roles,
)
from app.core.config import (
    AUTOMATION_AUTO_CERTIFICATES,
    AUTOMATION_CHANNELS,
    AUTOMATION_DRY_RUN,
    AUTOMATION_ENABLED,
    AUTOMATION_INTERVAL_HOURS,
)
from app.models.notification import NotificationLog
from app.models.user import User
from app.schemas.notification import (
    NotificationLogResponse,
    NotificationPreviewItem,
    NotificationPreviewResponse,
    NotificationRunRequest,
    NotificationRunResponse,
    NotificationSettingsResponse,
)
from app.services.mailer import smtp_configured
from app.services.notifications import (
    PlannedNotification,
    plan_notifications,
    run_notifications,
)
from app.services.whatsapp import whatsapp_configured


router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
NotificationsAdmin = require_roles("Super Admin", "Branch Admin")
NotificationsViewer = require_roles("Super Admin", "Branch Admin", "Staff")
NotificationsAccess = require_module("notifications")


def _item(plan: PlannedNotification) -> NotificationPreviewItem:
    return NotificationPreviewItem(
        category=plan.category,
        channel=plan.channel,
        recipient=plan.recipient,
        student_id=plan.student_id,
        student_name=plan.student_name,
        enrollment_id=plan.enrollment_id,
        branch_id=plan.branch_id,
        subject=plan.subject,
        status=plan.status,
        detail=plan.detail,
    )


@router.get(
    "/settings",
    response_model=NotificationSettingsResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def notification_settings(
    _: User = Depends(NotificationsViewer),
) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        email_configured=smtp_configured(),
        whatsapp_configured=whatsapp_configured(),
        automation_enabled=AUTOMATION_ENABLED,
        automation_dry_run=AUTOMATION_DRY_RUN,
        automation_channels=list(AUTOMATION_CHANNELS),
        automation_interval_hours=AUTOMATION_INTERVAL_HOURS,
        automation_auto_certificates=AUTOMATION_AUTO_CERTIFICATES,
    )


@router.get(
    "/logs",
    response_model=list[NotificationLogResponse],
    dependencies=[Depends(NotificationsAccess)],
)
def list_notification_logs(
    db: DatabaseSession,
    current_user: User = Depends(NotificationsViewer),
    category: str | None = Query(default=None, max_length=40),
    channel: str | None = Query(default=None, pattern=r"^(email|whatsapp)$"),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[NotificationLogResponse]:
    query = (
        select(NotificationLog)
        .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
        .limit(limit)
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(NotificationLog.branch_id == scope)
    if category:
        query = query.where(NotificationLog.category == category)
    if channel:
        query = query.where(NotificationLog.channel == channel)
    if status_filter:
        query = query.where(NotificationLog.status == status_filter)

    logs = db.scalars(query).all()
    return [
        NotificationLogResponse(
            id=log.id,
            category=log.category,
            template_key=log.template_key,
            channel=log.channel,
            status=log.status,
            recipient=log.recipient,
            subject=log.subject,
            message=log.message,
            error=log.error,
            branch_id=log.branch_id,
            student_id=log.student_id,
            student_name=log.student.full_name if log.student else None,
            enrollment_id=log.enrollment_id,
            triggered_by_id=log.triggered_by_id,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get(
    "/preview",
    response_model=NotificationPreviewResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def preview_notifications(
    db: DatabaseSession,
    current_user: User = Depends(NotificationsViewer),
    categories: list[str] = Query(
        default=["fee_reminder", "course_completion"]
    ),
    channels: list[str] = Query(default=["email"]),
    days_ahead: int = Query(default=7, ge=0, le=90),
) -> NotificationPreviewResponse:
    plans = plan_notifications(
        db,
        categories=categories,
        channels=channels,
        days_ahead=days_ahead,
        branch_id=branch_scope(current_user),
    )
    items = [_item(plan) for plan in plans]
    ready = sum(1 for item in items if item.status == "ready")
    return NotificationPreviewResponse(
        categories=categories,
        channels=channels,
        items=items,
        total=len(items),
        ready=ready,
        skipped=len(items) - ready,
    )


@router.post(
    "/run",
    response_model=NotificationRunResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def run_notification_jobs(
    payload: NotificationRunRequest,
    db: DatabaseSession,
    current_user: User = Depends(NotificationsAdmin),
) -> NotificationRunResponse:
    if not payload.dry_run and not payload.confirm_live:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Live delivery is blocked. Set confirm_live=true only when you "
                "intend to send real email/WhatsApp messages."
            ),
        )
    plans = run_notifications(
        db,
        categories=list(payload.categories),
        channels=list(payload.channels),
        days_ahead=payload.days_ahead,
        branch_id=branch_scope(current_user),
        dry_run=payload.dry_run,
        triggered_by_id=current_user.id,
    )
    if not payload.dry_run:
        record_audit(
            db,
            current_user.id,
            "notifications_run",
            "notification",
            0,
            {
                "categories": list(payload.categories),
                "channels": list(payload.channels),
                "days_ahead": payload.days_ahead,
                "sent": sum(1 for plan in plans if plan.status == "sent"),
                "failed": sum(1 for plan in plans if plan.status == "failed"),
                "skipped": sum(1 for plan in plans if plan.status == "skipped"),
            },
        )
        db.commit()

    return NotificationRunResponse(
        dry_run=payload.dry_run,
        categories=list(payload.categories),
        channels=list(payload.channels),
        sent=sum(1 for plan in plans if plan.status == "sent"),
        skipped=sum(1 for plan in plans if plan.status == "skipped"),
        failed=sum(1 for plan in plans if plan.status == "failed"),
        dry_run_count=sum(1 for plan in plans if plan.status == "dry_run"),
        items=[_item(plan) for plan in plans],
    )
