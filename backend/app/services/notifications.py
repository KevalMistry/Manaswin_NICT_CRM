"""Notification planning and delivery for automated reminders.

The institute already exposes on-demand fee reminder endpoints. This module
adds the missing scheduled/automated layer:

* fee reminders for instalments that are due soon or overdue;
* course-completion notices when an enrollment reaches its scheduled end date.

Nothing is delivered unless the operator configures SMTP/WhatsApp and asks for
a non-dry run. The daily scheduler is disabled by default and starts in
dry-run mode, so local and test environments never message real contacts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.batch import Batch
from app.models.certificate import Certificate
from app.models.enrollment import Enrollment
from app.models.fee import FeeInstallment, FeePlan
from app.models.notification import NotificationLog
from app.models.student import Student
from app.services.course_lifecycle import enrollment_course_timing
from app.services.email_templates import (
    EmailTemplateError,
    format_reminder_rows,
    render_email,
)
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    send_email,
    smtp_configured,
)
from app.services.whatsapp import (
    WhatsAppDeliveryError,
    WhatsAppNotConfigured,
    normalize_phone,
    send_whatsapp,
    whatsapp_configured,
)


CATEGORIES = ("fee_reminder", "course_completion")
CHANNELS = ("email", "whatsapp")
SENDABLE_STATUSES = ("ready",)


@dataclass
class PlannedNotification:
    category: str
    channel: str
    student_id: int
    student_name: str
    enrollment_id: int | None
    branch_id: int | None
    recipient: str | None
    subject: str | None
    message: str
    status: str = "ready"
    detail: str | None = None
    template_key: str | None = None


@dataclass
class _FeeGroup:
    enrollment: Enrollment
    student: Student
    installments: list[FeeInstallment] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _installment_status(due_date: date, today: date) -> str:
    overdue = (today - due_date).days
    if overdue > 0:
        return "Overdue"
    if overdue == 0:
        return "Due today"
    return "Due soon"


def _fee_groups(
    db: Session, branch_id: int | None, days_ahead: int
) -> list[_FeeGroup]:
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    query = (
        select(FeeInstallment)
        .options(
            joinedload(FeeInstallment.payments),
            joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.student),
            joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.course),
            joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.branch),
        )
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            Enrollment.status == "active",
            FeeInstallment.due_date <= cutoff,
        )
        .order_by(FeeInstallment.due_date.asc(), Enrollment.id.asc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)

    groups: dict[int, _FeeGroup] = {}
    for installment in db.scalars(query).unique().all():
        paid = sum((payment.amount for payment in installment.payments), Decimal("0"))
        if installment.amount - paid <= 0:
            continue
        enrollment = installment.fee_plan.enrollment
        group = groups.get(enrollment.id)
        if group is None:
            group = _FeeGroup(enrollment=enrollment, student=enrollment.student)
            groups[enrollment.id] = group
        group.installments.append(installment)
    return list(groups.values())


def _fee_message(group: _FeeGroup, today: date) -> tuple[str, str]:
    student = group.student
    branch_name = group.enrollment.batch.branch.name
    total = Decimal("0")
    lines = [
        f"Dear {student.full_name},",
        "",
        "This is a friendly reminder about the following pending fee instalment(s):",
        "",
    ]
    for installment in group.installments:
        paid = sum((payment.amount for payment in installment.payments), Decimal("0"))
        remaining = installment.amount - paid
        total += remaining
        lines.append(
            f"- {group.enrollment.batch.course.name} / {group.enrollment.batch.name}, "
            f"instalment {installment.installment_number}: INR {remaining:,.2f} "
            f"due {installment.due_date.isoformat()} "
            f"({_installment_status(installment.due_date, today)})"
        )
    lines += [
        "",
        f"Total pending: INR {total:,.2f}",
        "",
        "Please contact the branch office if you have already paid or need help.",
        "",
        "Thank you,",
        branch_name,
    ]
    return f"Fee payment reminder from {branch_name}", "\n".join(lines)


def _fee_context(group: _FeeGroup, today: date) -> dict[str, object]:
    total = Decimal("0")
    rows = []
    for installment in group.installments:
        paid = sum((payment.amount for payment in installment.payments), Decimal("0"))
        remaining = installment.amount - paid
        total += remaining
        rows.append(
            {
                "course": f"{group.enrollment.batch.course.name} / {group.enrollment.batch.name}",
                "installment": str(installment.installment_number),
                "amount": f"{remaining:,.2f}",
                "due": installment.due_date.isoformat(),
                "status": _installment_status(installment.due_date, today),
            }
        )
    return {
        "student_name": group.student.full_name,
        "branch_name": group.enrollment.batch.branch.name,
        "reminder_rows": format_reminder_rows(rows),
        "total_pending": f"{total:,.2f}",
    }


def _render_fee_email(db: Session, group: _FeeGroup, today: date):
    return render_email(
        db,
        "fee_reminder",
        _fee_context(group, today),
        branch_id=group.enrollment.batch.branch_id,
    )


def _recent_fee_reminders(db: Session, cooldown_days: int) -> set[tuple[int, str]]:
    if cooldown_days <= 0:
        return set()
    cutoff = _now() - timedelta(days=cooldown_days)
    rows = db.execute(
        select(NotificationLog.enrollment_id, NotificationLog.channel).where(
            NotificationLog.category == "fee_reminder",
            NotificationLog.status == "sent",
            NotificationLog.enrollment_id.is_not(None),
            NotificationLog.created_at >= cutoff,
        )
    ).all()
    return {(int(enrollment_id), channel) for enrollment_id, channel in rows}


def _completion_already_sent(db: Session, channel: str) -> set[int]:
    rows = db.scalars(
        select(NotificationLog.enrollment_id).where(
            NotificationLog.category == "course_completion",
            NotificationLog.channel == channel,
            NotificationLog.status == "sent",
            NotificationLog.enrollment_id.is_not(None),
        )
    ).all()
    return {int(enrollment_id) for enrollment_id in rows}


def _completion_message(enrollment: Enrollment, end_date: date) -> tuple[str, str]:
    student = enrollment.student
    course = enrollment.batch.course
    branch = enrollment.batch.branch
    subject = f"{course.name} course completion — {branch.name}"
    message = "\n".join(
        [
            f"Dear {student.full_name},",
            "",
            f"Your {course.name} course ({enrollment.batch.name}) reached its "
            f"scheduled end date on {end_date.isoformat()}.",
            "",
            "The institute is completing the final checks for your certificate "
            "(attendance, fees, examinations, assignments and online exams). "
            "You will be notified as soon as your certificate is ready.",
            "",
            "Congratulations on reaching this milestone.",
            "",
            "Thank you,",
            branch.name,
        ]
    )
    return subject, message


def _completion_context(enrollment: Enrollment, end_date: date) -> dict[str, object]:
    return {
        "student_name": enrollment.student.full_name,
        "course_name": enrollment.batch.course.name,
        "batch_name": enrollment.batch.name,
        "end_date": end_date.isoformat(),
        "branch_name": enrollment.batch.branch.name,
    }


def _render_completion_email(db: Session, enrollment: Enrollment, end_date: date):
    return render_email(
        db,
        "course_completion",
        _completion_context(enrollment, end_date),
        branch_id=enrollment.batch.branch_id,
    )


def plan_notifications(
    db: Session,
    *,
    categories: list[str],
    channels: list[str],
    days_ahead: int = 7,
    branch_id: int | None = None,
    cooldown_days: int = 3,
) -> list[PlannedNotification]:
    """Build the notification queue without sending anything."""
    plans: list[PlannedNotification] = []
    today = date.today()
    recent_fee = _recent_fee_reminders(db, cooldown_days)
    recent_completion = {
        channel: _completion_already_sent(db, channel) for channel in CHANNELS
    }

    def append_plan(
        *,
        category: str,
        channel: str,
        student: Student,
        enrollment: Enrollment,
        subject: str,
        message: str,
        already_sent: bool,
        template_key: str,
    ) -> None:
        if channel == "email":
            recipient = student.email
            configured = smtp_configured()
            missing_contact = "Student has no email address."
            not_configured = "Email delivery is not configured."
        else:
            recipient = normalize_phone(student.phone)
            configured = whatsapp_configured()
            missing_contact = "Student has no WhatsApp phone number."
            not_configured = "WhatsApp delivery is not configured."

        plan = PlannedNotification(
            category=category,
            channel=channel,
            student_id=student.id,
            student_name=student.full_name,
            enrollment_id=enrollment.id,
            branch_id=enrollment.batch.branch_id,
            recipient=recipient,
            subject=subject if channel == "email" else None,
            message=message,
            template_key=template_key,
        )
        if not recipient:
            plan.status = "skipped"
            plan.detail = missing_contact
        elif not configured:
            plan.status = "skipped"
            plan.detail = not_configured
        elif already_sent:
            plan.status = "skipped"
            plan.detail = (
                "Recently reminded; waiting for the cooldown window."
                if category == "fee_reminder"
                else "A completion notice was already sent."
            )
        plans.append(plan)

    if "fee_reminder" in categories:
        for group in _fee_groups(db, branch_id, days_ahead):
            try:
                rendered = _render_fee_email(db, group, today)
            except EmailTemplateError:
                continue
            for channel in channels:
                append_plan(
                    category="fee_reminder",
                    channel=channel,
                    student=group.student,
                    enrollment=group.enrollment,
                    subject=rendered.subject,
                    message=rendered.text,
                    already_sent=(group.enrollment.id, channel) in recent_fee,
                    template_key="fee_reminder",
                )

    if "course_completion" in categories:
        query = (
            select(Enrollment)
            .options(
                joinedload(Enrollment.student),
                joinedload(Enrollment.batch).joinedload(Batch.course),
                joinedload(Enrollment.batch).joinedload(Batch.branch),
            )
            .where(Enrollment.status == "active")
        )
        if branch_id is not None:
            query = query.join(Batch, Enrollment.batch_id == Batch.id).where(
                Batch.branch_id == branch_id
            )
        for enrollment in db.scalars(query).unique().all():
            end_date, _remaining, completed = enrollment_course_timing(enrollment)
            if not completed or end_date is None:
                continue
            existing_certificate = db.scalar(
                select(Certificate.id).where(
                    Certificate.enrollment_id == enrollment.id,
                    Certificate.document_type == "certificate",
                )
            )
            if existing_certificate is not None:
                continue
            try:
                rendered = _render_completion_email(db, enrollment, end_date)
            except EmailTemplateError:
                continue
            for channel in channels:
                append_plan(
                    category="course_completion",
                    channel=channel,
                    student=enrollment.student,
                    enrollment=enrollment,
                    subject=rendered.subject,
                    message=rendered.text,
                    already_sent=enrollment.id in recent_completion.get(channel, set()),
                    template_key="course_completion",
                )

    return plans


def deliver_notifications(
    db: Session,
    plans: list[PlannedNotification],
    *,
    dry_run: bool,
    triggered_by_id: int | None = None,
) -> None:
    """Send ready plans and persist a log row for each real attempt."""
    for plan in plans:
        if plan.status not in SENDABLE_STATUSES:
            continue
        if dry_run:
            plan.status = "dry_run"
            continue
        try:
            if plan.channel == "email":
                send_email(plan.recipient or "", plan.subject or "", plan.message)
            else:
                send_whatsapp(plan.recipient, plan.message)
            plan.status = "sent"
        except (
            MailNotConfigured,
            MailDeliveryError,
            WhatsAppNotConfigured,
            WhatsAppDeliveryError,
        ) as error:
            plan.status = "failed"
            plan.detail = str(error)
        except Exception as error:  # pragma: no cover - defensive
            plan.status = "failed"
            plan.detail = f"Unexpected delivery error: {error}"

    if dry_run:
        return

    for plan in plans:
        db.add(
            NotificationLog(
                category=plan.category,
                template_key=plan.template_key,
                channel=plan.channel,
                status=plan.status,
                recipient=plan.recipient,
                subject=plan.subject,
                message=plan.message,
                error=plan.detail if plan.status == "failed" else None,
                branch_id=plan.branch_id,
                student_id=plan.student_id,
                enrollment_id=plan.enrollment_id,
                triggered_by_id=triggered_by_id,
            )
        )
    db.commit()


def run_notifications(
    db: Session,
    *,
    categories: list[str],
    channels: list[str],
    days_ahead: int = 7,
    branch_id: int | None = None,
    dry_run: bool = True,
    triggered_by_id: int | None = None,
    cooldown_days: int = 3,
) -> list[PlannedNotification]:
    plans = plan_notifications(
        db,
        categories=categories,
        channels=channels,
        days_ahead=days_ahead,
        branch_id=branch_id,
        cooldown_days=cooldown_days,
    )
    deliver_notifications(
        db, plans, dry_run=dry_run, triggered_by_id=triggered_by_id
    )
    return plans
