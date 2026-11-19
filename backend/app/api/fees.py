from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.api.audit import record_audit
from app.models.batch import Batch
from app.models.course import Course
from app.models.branch import Branch
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.core.config import payment_emails_are_dry_run
from app.models.fee import FeeInstallment, FeePlan, Payment, PaymentClaim
from app.schemas.fee import (
    FeePlanCreate,
    FeePlanResponse,
    InstallmentCreate,
    PaymentCreate,
    PaymentResponse,
    FeeOverviewResponse,
    FeeInstallmentResponse,
    PaymentClaimApproveRequest,
    PaymentClaimRejectRequest,
    PaymentClaimResponse,
    ReceiptResponse,
    EmailDeliveryResponse,
    FeeReminderRow,
    FeeReminderSendRequest,
    FeeReminderSendResponse,
    WhatsAppDeliveryResponse,
)
from app.services.email_templates import (
    EmailTemplateError,
    format_reminder_rows,
    render_email,
    send_templated_email,
)
from app.services.fee_payments import (
    CLAIM_APPROVED,
    CLAIM_PENDING,
    CLAIM_REJECTED,
    claim_age_days,
    claim_is_duplicate,
    paid_total,
    remaining_amount,
)
from app.services.fee_receipt import (
    build_receipt,
    receipt_context,
    render_receipt_pdf,
)
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    smtp_configured,
)
from app.services.whatsapp import (
    WhatsAppDeliveryError,
    WhatsAppNotConfigured,
    send_whatsapp,
    whatsapp_configured,
)


router = APIRouter(prefix="/api/fees", tags=["Fees"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff")
FeesAccess = require_module("fees")


def check_branch(db: DatabaseSession, enrollment_id: int, current_user) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.batch))
        .where(Enrollment.id == enrollment_id)
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    check_branch_access(current_user, enrollment.batch.branch_id)
    return enrollment


def summarize_installment(installment: FeeInstallment) -> dict:
    """Return an installment with payment-derived status and totals.

    Stored ``status`` can drift from the payment records (for example legacy
    seeded rows), so the payable state is always derived from payments.
    """
    paid = sum((payment.amount for payment in installment.payments), Decimal("0.00"))
    remaining = installment.amount - paid
    if remaining <= 0:
        effective_status = "paid"
    elif paid > 0:
        effective_status = "partial"
    else:
        effective_status = "pending"
    return {
        "id": installment.id,
        "installment_number": installment.installment_number,
        "amount": installment.amount,
        "paid_amount": paid,
        "remaining_amount": remaining if remaining > 0 else Decimal("0.00"),
        "due_date": installment.due_date,
        "status": effective_status,
    }


@router.get("/overview", response_model=list[FeeOverviewResponse], dependencies=[Depends(FeesAccess)])
def fee_overview(
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> list[dict]:
    query = (
        select(Enrollment)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .join(Student, Enrollment.student_id == Student.id)
        .options(joinedload(Enrollment.batch).joinedload(Batch.course), joinedload(Enrollment.student))
        .where(Enrollment.status != "cancelled")
        .order_by(Enrollment.created_at.desc())
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Batch.branch_id == scope)
    result = []
    for enrollment in db.scalars(query).all():
        plan = db.scalar(select(FeePlan).where(FeePlan.enrollment_id == enrollment.id))
        installments = []
        total_paid = Decimal("0.00")
        if plan:
            installment_rows = list(db.scalars(
                select(FeeInstallment).where(FeeInstallment.fee_plan_id == plan.id).order_by(FeeInstallment.installment_number)
            ).all())
            installments = [summarize_installment(installment) for installment in installment_rows]
            total_paid = sum((item["paid_amount"] for item in installments), Decimal("0"))
        total_fee = (plan.total_amount - plan.discount_amount - plan.scholarship_amount) if plan else Decimal("0.00")
        result.append({
            "enrollment_id": enrollment.id,
            "student_id": enrollment.student_id,
            "student_name": enrollment.student.full_name,
            "enrollment_code": enrollment.enrollment_code,
            "batch_id": enrollment.batch_id,
            "admission_date": enrollment.admission_date,
            "course_name": enrollment.batch.course.name,
            "course_fee": enrollment.batch.course.fee_amount,
            "fee_plan": plan,
            "installments": installments,
            "total_paid": total_paid,
            "balance": total_fee - total_paid,
        })
    return result


@router.post(
    "/plans",
    response_model=FeePlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FeesAccess)],
)
def create_fee_plan(
    payload: FeePlanCreate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> FeePlan:
    enrollment = check_branch(db, payload.enrollment_id, current_user)
    if db.scalar(select(FeePlan).where(FeePlan.enrollment_id == enrollment.id)):
        raise HTTPException(status_code=409, detail="Fee plan already exists")
    net_amount = (
        payload.total_amount
        - payload.discount_amount
        - payload.scholarship_amount
    ).quantize(Decimal("0.01"))
    installment_total = sum(
        (item.amount for item in payload.installments), Decimal("0")
    ).quantize(Decimal("0.01"))
    if net_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Net fee after discounts and scholarship must be greater than zero",
        )
    # The UI splits an amount into N equal installments. Splitting can produce a
    # one-paise rounding difference, so absorb that into the largest installment
    # rather than rejecting an otherwise valid plan.
    difference = (net_amount - installment_total).quantize(Decimal("0.01"))
    if abs(difference) > Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail="Installments must equal total amount after discounts and scholarship",
        )
    if difference != 0:
        largest = max(payload.installments, key=lambda item: item.amount)
        largest.amount = (largest.amount + difference).quantize(Decimal("0.01"))
        if largest.amount <= 0:
            raise HTTPException(
                status_code=400, detail="Installment amounts must be greater than zero"
            )
    numbers = [item.installment_number for item in payload.installments]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(status_code=400, detail="Installment numbers must be unique")
    plan = FeePlan(
        enrollment_id=payload.enrollment_id,
        total_amount=payload.total_amount,
        discount_amount=payload.discount_amount,
        scholarship_amount=payload.scholarship_amount,
        installments=[
            FeeInstallment(**item.model_dump()) for item in payload.installments
        ],
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/plans/{enrollment_id}", response_model=FeePlanResponse, dependencies=[Depends(FeesAccess)])
def get_fee_plan(
    enrollment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> FeePlan:
    check_branch(db, enrollment_id, current_user)
    plan = db.scalar(select(FeePlan).where(FeePlan.enrollment_id == enrollment_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="Fee plan not found")
    return plan


@router.post(
    "/installments/{installment_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FeesAccess)],
)
def record_payment(
    installment_id: int,
    payload: PaymentCreate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> Payment:
    installment = db.scalar(
        select(FeeInstallment)
        .options(joinedload(FeeInstallment.fee_plan).joinedload(FeePlan.enrollment).joinedload(Enrollment.batch))
        .where(FeeInstallment.id == installment_id)
        .with_for_update()
    )
    if installment is None:
        raise HTTPException(status_code=404, detail="Installment not found")
    enrollment = installment.fee_plan.enrollment
    check_branch(db, enrollment.id, current_user)
    if enrollment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot record a payment for a cancelled enrollment",
        )
    paid = sum((payment.amount for payment in installment.payments), Decimal("0"))
    if paid + payload.amount > installment.amount:
        raise HTTPException(status_code=400, detail="Payment exceeds installment balance")
    receipt_number = payload.receipt_number or f"RCT-{datetime.now().year}-{uuid4().hex[:8].upper()}"
    if db.scalar(select(Payment.id).where(Payment.receipt_number == receipt_number)) is not None:
        raise HTTPException(status_code=409, detail="Receipt number already exists")
    payment = Payment(
        receipt_number=receipt_number,
        installment_id=installment_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        payment_date=payload.payment_date,
    )
    db.add(payment)
    installment.status = "paid" if paid + payload.amount == installment.amount else "partial"
    db.flush()
    record_audit(
        db,
        current_user.id,
        "fee_payment_recorded",
        "payment",
        payment.id,
        {"installment_id": installment.id, "amount": str(payload.amount)},
    )
    db.commit()
    db.refresh(payment)
    return payment


def load_payment_for_user(
    db: DatabaseSession, payment_id: int, current_user
) -> Payment:
    payment = db.scalar(
        select(Payment)
        .options(
            joinedload(Payment.installment)
            .joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.student),
            joinedload(Payment.installment)
            .joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.course),
            joinedload(Payment.installment)
            .joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.branch),
        )
        .where(Payment.id == payment_id)
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    enrollment = payment.installment.fee_plan.enrollment
    check_branch(db, enrollment.id, current_user)
    return payment


@router.get("/payments/{payment_id}/receipt", response_model=ReceiptResponse, dependencies=[Depends(FeesAccess)])
def payment_receipt(
    payment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> ReceiptResponse:
    return build_receipt(load_payment_for_user(db, payment_id, current_user))


@router.get(
    "/payments/{payment_id}/receipt.pdf",
    dependencies=[Depends(FeesAccess)],
    response_class=Response,
)
def payment_receipt_pdf(
    payment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> Response:
    payment = load_payment_for_user(db, payment_id, current_user)
    pdf = render_receipt_pdf(build_receipt(payment))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{payment.receipt_number}.pdf"'
            )
        },
    )


def send_receipt_email(
    db: DatabaseSession,
    payment: Payment,
    *,
    triggered_by_id: int | None,
    dry_run: bool | None = None,
) -> tuple[str, str | None]:
    receipt = build_receipt(payment)
    if not receipt.student_email:
        raise HTTPException(
            status_code=400,
            detail="This student does not have an email address on record",
        )
    enrollment = payment.installment.fee_plan.enrollment
    pdf = render_receipt_pdf(receipt)
    try:
        return send_templated_email(
            db,
            key="fee_receipt",
            recipient=receipt.student_email,
            context=receipt_context(receipt),
            branch_id=enrollment.batch.branch_id,
            category="fee_receipt",
            student_id=enrollment.student_id,
            enrollment_id=enrollment.id,
            triggered_by_id=triggered_by_id,
            dry_run=payment_emails_are_dry_run() if dry_run is None else dry_run,
            attachments=[
                (f"receipt-{receipt.receipt_number}.pdf", pdf, "application/pdf")
            ],
        )
    except EmailTemplateError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post(
    "/payments/{payment_id}/email-receipt",
    response_model=EmailDeliveryResponse,
    dependencies=[Depends(FeesAccess)],
)
def email_payment_receipt(
    payment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> EmailDeliveryResponse:
    payment = load_payment_for_user(db, payment_id, current_user)
    receipt = build_receipt(payment)
    if not receipt.student_email:
        raise HTTPException(
            status_code=400,
            detail="This student does not have an email address on record",
        )
    if not payment_emails_are_dry_run() and not smtp_configured():
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured. Set SMTP_HOST and SMTP_FROM.",
        )

    try:
        status, detail = send_receipt_email(
            db, payment, triggered_by_id=current_user.id
        )
    except MailDeliveryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    record_audit(
        db,
        current_user.id,
        "fee_receipt_emailed",
        "payment",
        payment.id,
        {"recipient": receipt.student_email, "delivery_status": status},
    )
    db.commit()
    if status == "dry_run":
        return EmailDeliveryResponse(
            sent=False,
            recipient=receipt.student_email,
            status=status,
            message=(
                "Receipt generated but not emailed because FEE_RECEIPT_EMAIL_MODE "
                "is set to dry_run."
            ),
        )
    return EmailDeliveryResponse(
        sent=True,
        recipient=receipt.student_email,
        status=status,
        message=f"Receipt emailed to {receipt.student_email}",
    )


def _reminder_rows(
    db: DatabaseSession, current_user, days_ahead: int
) -> list[FeeReminderRow]:
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
            Enrollment.status != "cancelled",
            FeeInstallment.due_date <= cutoff,
        )
        .order_by(FeeInstallment.due_date.asc(), Enrollment.id.asc())
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Batch.branch_id == scope)

    rows: list[FeeReminderRow] = []
    for installment in db.scalars(query).unique().all():
        paid = sum((payment.amount for payment in installment.payments), Decimal("0"))
        remaining = installment.amount - paid
        if remaining <= 0:
            continue
        enrollment = installment.fee_plan.enrollment
        student = enrollment.student
        overdue = (today - installment.due_date).days
        if overdue > 0:
            status = "Overdue"
        elif overdue == 0:
            status = "Due today"
        else:
            status = "Due soon"
        rows.append(
            FeeReminderRow(
                installment_id=installment.id,
                enrollment_id=enrollment.id,
                student_id=student.id,
                student_name=student.full_name,
                student_code=student.student_code,
                email=student.email,
                phone=student.phone,
                course_name=enrollment.batch.course.name,
                batch_name=enrollment.batch.name,
                branch_id=enrollment.batch.branch_id,
                branch_name=enrollment.batch.branch.name,
                installment_number=installment.installment_number,
                remaining_amount=remaining,
                due_date=installment.due_date,
                days_overdue=max(overdue, 0),
                status=status,
            )
        )
    return rows


@router.get(
    "/reminders",
    response_model=list[FeeReminderRow],
    dependencies=[Depends(FeesAccess)],
)
def fee_reminders(
    db: DatabaseSession,
    current_user=Depends(AdminUser),
    days_ahead: int = Query(default=7, ge=0, le=90),
) -> list[FeeReminderRow]:
    return _reminder_rows(db, current_user, days_ahead)


def _reminder_context(rows: list[FeeReminderRow]) -> dict[str, object]:
    total = sum((row.remaining_amount for row in rows), Decimal("0"))
    table = [
        {
            "course": f"{row.course_name} / {row.batch_name}",
            "installment": str(row.installment_number),
            "amount": f"{row.remaining_amount:,.2f}",
            "due": row.due_date.isoformat(),
            "status": row.status,
        }
        for row in rows
    ]
    return {
        "student_name": rows[0].student_name,
        "branch_name": rows[0].branch_name,
        "reminder_rows": format_reminder_rows(table),
        "total_pending": f"{total:,.2f}",
    }


@router.post(
    "/reminders/send",
    response_model=FeeReminderSendResponse,
    dependencies=[Depends(FeesAccess)],
)
def send_fee_reminders(
    payload: FeeReminderSendRequest,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> FeeReminderSendResponse:
    if not smtp_configured():
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured. Set SMTP_HOST and SMTP_FROM.",
        )

    rows = _reminder_rows(db, current_user, payload.days_ahead)
    if payload.installment_ids is not None:
        wanted = set(payload.installment_ids)
        rows = [row for row in rows if row.installment_id in wanted]
    if not rows:
        raise HTTPException(
            status_code=400, detail="No pending instalments match this reminder"
        )

    grouped: dict[int, list[FeeReminderRow]] = {}
    for row in rows:
        grouped.setdefault(row.student_id, []).append(row)

    recipients: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for student_rows in grouped.values():
        email = student_rows[0].email
        if not email:
            skipped.append(student_rows[0].student_name)
            continue
        try:
            send_templated_email(
                db,
                key="fee_reminder",
                recipient=email,
                context=_reminder_context(student_rows),
                branch_id=student_rows[0].branch_id,
                category="fee_reminder",
                student_id=student_rows[0].student_id,
                enrollment_id=student_rows[0].enrollment_id,
                triggered_by_id=current_user.id,
            )
            recipients.append(email)
        except (MailNotConfigured, MailDeliveryError, EmailTemplateError):
            failed.append(email)

    record_audit(
        db,
        current_user.id,
        "fee_reminders_sent",
        "fee_reminder",
        0,
        {
            "sent": len(recipients),
            "skipped": len(skipped),
            "failed": len(failed),
            "instalments": len(rows),
        },
    )
    db.commit()
    return FeeReminderSendResponse(
        sent_count=len(recipients),
        skipped_count=len(skipped),
        failed_count=len(failed),
        recipients=recipients,
        skipped=skipped,
        failed=failed,
    )


@router.post(
    "/payments/{payment_id}/whatsapp-receipt",
    response_model=WhatsAppDeliveryResponse,
    dependencies=[Depends(FeesAccess)],
)
def whatsapp_payment_receipt(
    payment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> WhatsAppDeliveryResponse:
    payment = load_payment_for_user(db, payment_id, current_user)
    receipt = build_receipt(payment)
    if not receipt.student_phone:
        raise HTTPException(
            status_code=400,
            detail="This student does not have a phone number on record",
        )
    if not whatsapp_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "WhatsApp delivery is not configured. Set WHATSAPP_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID."
            ),
        )

    enrollment = payment.installment.fee_plan.enrollment
    try:
        rendered = render_email(
            db,
            "fee_receipt",
            receipt_context(receipt),
            branch_id=enrollment.batch.branch_id,
        )
    except EmailTemplateError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        recipient = send_whatsapp(receipt.student_phone, rendered.text)
    except WhatsAppNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WhatsAppDeliveryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    record_audit(
        db,
        current_user.id,
        "fee_receipt_whatsapped",
        "payment",
        payment.id,
        {"recipient": recipient},
    )
    db.commit()
    return WhatsAppDeliveryResponse(
        sent=True,
        recipient=recipient,
        message=f"Receipt sent on WhatsApp to {recipient}",
    )


@router.post(
    "/reminders/send-whatsapp",
    response_model=FeeReminderSendResponse,
    dependencies=[Depends(FeesAccess)],
)
def send_fee_reminders_whatsapp(
    payload: FeeReminderSendRequest,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> FeeReminderSendResponse:
    if not whatsapp_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "WhatsApp delivery is not configured. Set WHATSAPP_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID."
            ),
        )

    rows = _reminder_rows(db, current_user, payload.days_ahead)
    if payload.installment_ids is not None:
        wanted = set(payload.installment_ids)
        rows = [row for row in rows if row.installment_id in wanted]
    if not rows:
        raise HTTPException(
            status_code=400, detail="No pending instalments match this reminder"
        )

    grouped: dict[int, list[FeeReminderRow]] = {}
    for row in rows:
        grouped.setdefault(row.student_id, []).append(row)

    recipients: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for student_rows in grouped.values():
        phone = student_rows[0].phone
        if not phone:
            skipped.append(student_rows[0].student_name)
            continue
        context = _reminder_context(student_rows)
        try:
            rendered = render_email(
                db,
                "fee_reminder",
                context,
                branch_id=student_rows[0].branch_id,
            )
            recipients.append(send_whatsapp(phone, rendered.text))
        except (WhatsAppNotConfigured, WhatsAppDeliveryError, EmailTemplateError):
            failed.append(student_rows[0].student_name)

    record_audit(
        db,
        current_user.id,
        "fee_reminders_whatsapped",
        "fee_reminder",
        0,
        {
            "sent": len(recipients),
            "skipped": len(skipped),
            "failed": len(failed),
            "instalments": len(rows),
        },
    )
    db.commit()
    return FeeReminderSendResponse(
        sent_count=len(recipients),
        skipped_count=len(skipped),
        failed_count=len(failed),
        recipients=recipients,
        skipped=skipped,
        failed=failed,
    )


@router.get("/installments/{enrollment_id}", dependencies=[Depends(FeesAccess)])
def list_installments(
    enrollment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> list[dict]:
    check_branch(db, enrollment_id, current_user)
    installments = list(
        db.scalars(
            select(FeeInstallment)
            .join(FeePlan)
            .where(FeePlan.enrollment_id == enrollment_id)
            .order_by(FeeInstallment.installment_number)
        ).all()
    )
    return [summarize_installment(item) for item in installments]


def _claim_load_options():
    return (
        joinedload(PaymentClaim.installment)
        .joinedload(FeeInstallment.fee_plan)
        .joinedload(FeePlan.enrollment)
        .joinedload(Enrollment.student),
        joinedload(PaymentClaim.installment)
        .joinedload(FeeInstallment.fee_plan)
        .joinedload(FeePlan.enrollment)
        .joinedload(Enrollment.batch)
        .joinedload(Batch.course),
        joinedload(PaymentClaim.installment)
        .joinedload(FeeInstallment.fee_plan)
        .joinedload(FeePlan.enrollment)
        .joinedload(Enrollment.batch)
        .joinedload(Batch.branch),
        joinedload(PaymentClaim.student),
        joinedload(PaymentClaim.branch),
        joinedload(PaymentClaim.reviewed_by),
        joinedload(PaymentClaim.payment),
    )


def load_claim_for_user(
    db: DatabaseSession, claim_id: int, current_user
) -> PaymentClaim:
    claim = db.scalar(
        select(PaymentClaim)
        .options(*_claim_load_options())
        .where(PaymentClaim.id == claim_id)
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Payment claim not found")
    check_branch_access(current_user, claim.branch_id)
    return claim


def claim_response(claim: PaymentClaim) -> PaymentClaimResponse:
    enrollment = claim.installment.fee_plan.enrollment
    return PaymentClaimResponse(
        id=claim.id,
        installment_id=claim.installment_id,
        installment_number=claim.installment.installment_number,
        student_id=claim.student_id,
        student_name=claim.student.full_name,
        student_code=claim.student.student_code,
        student_email=claim.student.email,
        course_name=enrollment.batch.course.name,
        batch_name=enrollment.batch.name,
        branch_id=claim.branch_id,
        branch_name=claim.branch.name,
        amount=claim.amount,
        upi_reference=claim.upi_reference,
        paid_on=claim.paid_on,
        status=claim.status,
        submitted_at=claim.submitted_at,
        reviewed_by_name=claim.reviewed_by.full_name if claim.reviewed_by else None,
        reviewed_at=claim.reviewed_at,
        rejection_code=claim.rejection_code,
        rejection_reason=claim.rejection_reason,
        staff_note=claim.staff_note,
        payment_id=claim.payment_id,
        receipt_number=claim.payment.receipt_number if claim.payment else None,
        receipt_email_status=claim.receipt_email_status,
        receipt_email_detail=claim.receipt_email_detail,
        age_days=claim_age_days(claim),
    )


@router.get(
    "/payment-claims",
    response_model=list[PaymentClaimResponse],
    dependencies=[Depends(FeesAccess)],
)
def list_payment_claims(
    db: DatabaseSession,
    current_user=Depends(AdminUser),
    claim_status: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(pending|approved|rejected|cancelled)$",
    ),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[PaymentClaimResponse]:
    query = (
        select(PaymentClaim)
        .options(*_claim_load_options())
        .order_by(PaymentClaim.submitted_at.desc(), PaymentClaim.id.desc())
        .limit(limit)
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(PaymentClaim.branch_id == scope)
    if claim_status:
        query = query.where(PaymentClaim.status == claim_status)
    return [claim_response(claim) for claim in db.scalars(query).unique().all()]


@router.post(
    "/payment-claims/{claim_id}/approve",
    response_model=PaymentClaimResponse,
    dependencies=[Depends(FeesAccess)],
)
def approve_payment_claim(
    claim_id: int,
    payload: PaymentClaimApproveRequest,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> PaymentClaimResponse:
    claim = load_claim_for_user(db, claim_id, current_user)
    if claim.status != CLAIM_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Only pending claims can be approved (this claim is {claim.status})",
        )

    installment = claim.installment
    paid_before = paid_total(installment)
    remaining = remaining_amount(db, installment)
    if claim.amount > remaining:
        raise HTTPException(
            status_code=400,
            detail=(
                "The claimed amount exceeds the remaining installment balance of "
                f"INR {remaining:,.2f}. Reject the claim and ask the student to "
                "submit the correct amount."
            ),
        )
    if claim_is_duplicate(db, claim.upi_reference, exclude_claim_id=claim.id):
        raise HTTPException(
            status_code=400,
            detail="Another pending or approved claim already uses this UPI reference",
        )

    payment = Payment(
        receipt_number=f"RCT-{datetime.now().year}-{uuid4().hex[:8].upper()}",
        installment_id=claim.installment_id,
        amount=claim.amount,
        payment_method="upi",
        payment_date=claim.paid_on,
        reference=claim.upi_reference,
    )
    db.add(payment)
    db.flush()

    claim.status = CLAIM_APPROVED
    claim.reviewed_by_id = current_user.id
    claim.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    claim.staff_note = payload.staff_note
    claim.payment_id = payment.id
    installment.status = (
        "paid" if paid_before + claim.amount >= installment.amount else "partial"
    )

    try:
        email_status, email_detail = send_receipt_email(
            db, payment, triggered_by_id=current_user.id
        )
        claim.receipt_email_status = email_status
        claim.receipt_email_detail = email_detail
    except (HTTPException, MailDeliveryError) as error:
        claim.receipt_email_status = "failed"
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        claim.receipt_email_detail = str(detail)

    record_audit(
        db,
        current_user.id,
        "payment_claim_approved",
        "payment_claim",
        claim.id,
        {
            "payment_id": payment.id,
            "installment_id": installment.id,
            "amount": str(claim.amount),
            "upi_reference": claim.upi_reference,
            "receipt_email_status": claim.receipt_email_status,
        },
    )
    db.commit()
    return claim_response(load_claim_for_user(db, claim.id, current_user))


@router.post(
    "/payment-claims/{claim_id}/reject",
    response_model=PaymentClaimResponse,
    dependencies=[Depends(FeesAccess)],
)
def reject_payment_claim(
    claim_id: int,
    payload: PaymentClaimRejectRequest,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> PaymentClaimResponse:
    claim = load_claim_for_user(db, claim_id, current_user)
    if claim.status != CLAIM_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Only pending claims can be rejected (this claim is {claim.status})",
        )

    claim.status = CLAIM_REJECTED
    claim.reviewed_by_id = current_user.id
    claim.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    claim.rejection_code = payload.rejection_code
    claim.rejection_reason = payload.rejection_reason
    claim.staff_note = payload.staff_note

    enrollment = claim.installment.fee_plan.enrollment
    if claim.student.email:
        branch = claim.branch
        context = {
            "student_name": claim.student.full_name,
            "course_name": enrollment.batch.course.name,
            "batch_name": enrollment.batch.name,
            "amount": f"{claim.amount:,.2f}",
            "upi_reference": claim.upi_reference,
            "rejection_reason": claim.rejection_reason,
            "branch_name": branch.name,
            "branch_phone_suffix": f" on {branch.phone}" if branch.phone else "",
        }
        try:
            email_status, email_detail = send_templated_email(
                db,
                key="payment_rejected",
                recipient=claim.student.email,
                context=context,
                branch_id=claim.branch_id,
                category="payment_rejected",
                student_id=claim.student_id,
                enrollment_id=enrollment.id,
                triggered_by_id=current_user.id,
                dry_run=payment_emails_are_dry_run(),
            )
            claim.receipt_email_status = email_status
            claim.receipt_email_detail = email_detail
        except (EmailTemplateError, MailDeliveryError) as error:
            claim.receipt_email_status = "failed"
            claim.receipt_email_detail = str(error)

    record_audit(
        db,
        current_user.id,
        "payment_claim_rejected",
        "payment_claim",
        claim.id,
        {
            "amount": str(claim.amount),
            "upi_reference": claim.upi_reference,
            "rejection_code": claim.rejection_code,
        },
    )
    db.commit()
    return claim_response(load_claim_for_user(db, claim.id, current_user))
