from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.api.audit import record_audit
from app.api.dependencies import DatabaseSession, require_roles
from app.core.config import payment_emails_are_dry_run
from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.certificate import Certificate
from app.models.enrollment import Enrollment
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment, PaymentClaim
from app.models.student import Student
from app.models.user import User
from app.schemas.fee import PaymentClaimCreate, PaymentClaimResponse
from app.schemas.student_portal import (
    StudentPortalAttendance,
    StudentPortalCertificate,
    StudentPortalClaim,
    StudentPortalEnrollment,
    StudentPortalInstallment,
    StudentPortalPayment,
    StudentPortalResponse,
    StudentPortalResult,
)
from app.services.email_templates import (
    EmailTemplateError,
    send_templated_email,
)
from app.services.fee_payments import (
    CLAIM_CANCELLED,
    CLAIM_PENDING,
    claim_is_duplicate,
    pending_claim_total,
    remaining_amount,
)
from app.services.fee_receipt import build_receipt, render_receipt_pdf
from app.services.mailer import MailDeliveryError


router = APIRouter(prefix="/api/student-portal", tags=["Student Portal"])
StudentUser = require_roles("Student")


def _current_student(db: DatabaseSession, current_user: User) -> Student:
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.user))
        .where(Student.user_id == current_user.id, Student.is_active.is_(True))
    )
    if student is None:
        raise HTTPException(
            status_code=403,
            detail="No active student profile is linked to this account",
        )
    return student


def _claim_portal_row(claim: PaymentClaim) -> StudentPortalClaim:
    return StudentPortalClaim(
        id=claim.id,
        installment_id=claim.installment_id,
        installment_number=claim.installment.installment_number,
        amount=claim.amount,
        upi_reference=claim.upi_reference,
        paid_on=claim.paid_on,
        status=claim.status,
        submitted_at=claim.submitted_at,
        reviewed_at=claim.reviewed_at,
        rejection_code=claim.rejection_code,
        rejection_reason=claim.rejection_reason,
        staff_note=claim.staff_note,
        payment_id=claim.payment_id,
        receipt_number=claim.payment.receipt_number if claim.payment else None,
    )


def _claim_staff_row(claim: PaymentClaim) -> PaymentClaimResponse:
    enrollment = claim.installment.fee_plan.enrollment
    from app.services.fee_payments import claim_age_days

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


def _load_own_claim(
    db: DatabaseSession, claim_id: int, student: Student
) -> PaymentClaim:
    claim = db.scalar(
        select(PaymentClaim)
        .options(
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
        .where(PaymentClaim.id == claim_id, PaymentClaim.student_id == student.id)
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Payment claim not found")
    return claim


@router.get("/me", response_model=StudentPortalResponse)
def get_student_portal(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentPortalResponse:
    student = _current_student(db, current_user)

    enrollments = db.scalars(
        select(Enrollment)
        .options(
            joinedload(Enrollment.batch).joinedload(Batch.course),
            joinedload(Enrollment.batch).joinedload(Batch.branch),
            joinedload(Enrollment.fee_plan)
            .joinedload(FeePlan.installments)
            .joinedload(FeeInstallment.payments),
        )
        .where(Enrollment.student_id == student.id)
        .order_by(Enrollment.admission_date.desc())
    ).unique().all()

    claim_rows = db.scalars(
        select(PaymentClaim)
        .options(
            joinedload(PaymentClaim.installment)
            .joinedload(FeeInstallment.fee_plan),
            joinedload(PaymentClaim.payment),
        )
        .where(PaymentClaim.student_id == student.id)
        .order_by(PaymentClaim.submitted_at.desc(), PaymentClaim.id.desc())
    ).unique().all()
    claims_by_enrollment: dict[int, list[PaymentClaim]] = {}
    for claim in claim_rows:
        enrollment_id = claim.installment.fee_plan.enrollment_id
        claims_by_enrollment.setdefault(enrollment_id, []).append(claim)

    enrollment_data = []
    for enrollment in enrollments:
        plan = enrollment.fee_plan
        installments = []
        payments = []
        total_paid = Decimal("0")
        if plan:
            for installment in plan.installments:
                paid = sum(
                    (payment.amount for payment in installment.payments), Decimal("0")
                )
                total_paid += paid
                pending = pending_claim_total(db, installment.id)
                remaining = max(installment.amount - paid, Decimal("0"))
                installments.append(
                    StudentPortalInstallment(
                        id=installment.id,
                        installment_number=installment.installment_number,
                        amount=installment.amount,
                        due_date=installment.due_date,
                        status=installment.status,
                        paid=paid,
                        pending_claim_amount=pending,
                        claimable_amount=max(remaining - pending, Decimal("0")),
                    )
                )
                for payment in installment.payments:
                    payments.append(
                        StudentPortalPayment(
                            payment_id=payment.id,
                            receipt_number=payment.receipt_number,
                            installment_number=installment.installment_number,
                            amount=payment.amount,
                            payment_method=payment.payment_method,
                            payment_date=payment.payment_date,
                            reference=payment.reference,
                        )
                    )
        payments.sort(key=lambda item: (item.payment_date, item.payment_id), reverse=True)
        total_fee = (
            plan.total_amount - plan.discount_amount - plan.scholarship_amount
            if plan
            else Decimal("0")
        )
        branch = enrollment.batch.branch
        enrollment_data.append(
            StudentPortalEnrollment(
                enrollment_id=enrollment.id,
                enrollment_code=enrollment.enrollment_code,
                batch_name=enrollment.batch.name,
                course_name=enrollment.batch.course.name,
                status=enrollment.status,
                branch_id=enrollment.batch.branch_id,
                branch_name=branch.name,
                upi_id=branch.upi_id,
                upi_payee_name=branch.upi_payee_name,
                upi_qr_code_url=branch.upi_qr_code_url,
                total_fee=total_fee,
                total_paid=total_paid,
                balance=total_fee - total_paid,
                installments=installments,
                payments=payments,
                claims=[
                    _claim_portal_row(claim)
                    for claim in claims_by_enrollment.get(enrollment.id, [])
                ],
            )
        )

    attendance_rows = db.execute(
        select(
            Enrollment.enrollment_code,
            func.count(Attendance.id),
            func.sum(case((Attendance.status == "present", 1), else_=0)),
            func.sum(case((Attendance.status == "late", 1), else_=0)),
            func.sum(case((Attendance.status == "absent", 1), else_=0)),
        )
        .join(Attendance, Attendance.enrollment_id == Enrollment.id)
        .where(Enrollment.student_id == student.id)
        .group_by(Enrollment.id, Enrollment.enrollment_code)
    ).all()
    attendance_data = [
        StudentPortalAttendance(
            enrollment_code=row[0],
            total=int(row[1] or 0),
            present=int(row[2] or 0),
            late=int(row[3] or 0),
            absent=int(row[4] or 0),
            percentage=round(((int(row[2] or 0) + int(row[3] or 0)) / int(row[1])) * 100, 2) if row[1] else 0,
        )
        for row in attendance_rows
    ]

    result_rows = db.execute(
        select(Examination.name, Examination.exam_date, ExamSubject.name, ExamMark.marks_obtained, ExamSubject.max_marks, ExamMark.grade)
        .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
        .join(Examination, ExamSubject.examination_id == Examination.id)
        .join(Enrollment, ExamMark.enrollment_id == Enrollment.id)
        .where(Enrollment.student_id == student.id, Examination.is_published.is_(True))
        .order_by(Examination.exam_date.desc(), ExamSubject.name)
    ).all()
    results = [StudentPortalResult(
        examination=row[0], exam_date=row[1], subject=row[2],
        marks_obtained=row[3], maximum_marks=row[4], grade=row[5],
    ) for row in result_rows]

    certificates = [
        StudentPortalCertificate(
            id=certificate.id,
            certificate_number=certificate.certificate_number,
            verification_code=certificate.verification_code,
            document_type=certificate.document_type,
            issue_date=certificate.issue_date,
            grade=certificate.grade,
            percentage=certificate.percentage,
            is_valid=certificate.is_valid,
        )
        for certificate in db.scalars(
            select(Certificate).join(Enrollment).where(Enrollment.student_id == student.id)
        ).all()
    ]
    return StudentPortalResponse(
        student_code=student.student_code,
        full_name=student.full_name,
        email=student.email,
        phone=student.phone,
        enrollments=enrollment_data,
        attendance=attendance_data,
        results=results,
        certificates=certificates,
    )


@router.get(
    "/payment-claims",
    response_model=list[PaymentClaimResponse],
)
def list_own_claims(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> list[PaymentClaimResponse]:
    student = _current_student(db, current_user)
    claims = db.scalars(
        select(PaymentClaim)
        .options(
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
        .where(PaymentClaim.student_id == student.id)
        .order_by(PaymentClaim.submitted_at.desc(), PaymentClaim.id.desc())
    ).unique().all()
    return [_claim_staff_row(claim) for claim in claims]


@router.post(
    "/installments/{installment_id}/claims",
    response_model=PaymentClaimResponse,
    status_code=201,
)
def submit_payment_claim(
    installment_id: int,
    payload: PaymentClaimCreate,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> PaymentClaimResponse:
    student = _current_student(db, current_user)
    installment = db.scalar(
        select(FeeInstallment)
        .options(
            joinedload(FeeInstallment.payments),
            joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.course),
            joinedload(FeeInstallment.fee_plan)
            .joinedload(FeePlan.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.branch),
        )
        .where(FeeInstallment.id == installment_id)
    )
    if installment is None:
        raise HTTPException(status_code=404, detail="Fee installment not found")
    enrollment = installment.fee_plan.enrollment
    if enrollment.student_id != student.id:
        raise HTTPException(status_code=403, detail="This installment is not yours")
    if enrollment.status == "cancelled":
        raise HTTPException(status_code=400, detail="This enrollment is cancelled")

    branch = enrollment.batch.branch
    if not branch.upi_id or not branch.upi_payee_name:
        raise HTTPException(
            status_code=409,
            detail=(
                "Online UPI payment is not enabled for this branch. "
                "Please pay at the branch office or contact the administrator."
            ),
        )
    if payload.paid_on > date.today():
        raise HTTPException(status_code=400, detail="Payment date cannot be in the future")

    claimable = remaining_amount(db, installment) - pending_claim_total(
        db, installment.id
    )
    claimable = max(claimable, Decimal("0"))
    if claimable <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "This installment has no payable balance left. Any submitted UPI "
                "payment is already awaiting verification."
            ),
        )
    if payload.amount > claimable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"You can submit at most INR {claimable:,.2f} for this installment "
                "(the unpaid balance minus claims already awaiting verification)."
            ),
        )
    if claim_is_duplicate(db, payload.upi_reference):
        raise HTTPException(
            status_code=409,
            detail="A payment claim with this UPI reference already exists",
        )

    claim = PaymentClaim(
        installment_id=installment.id,
        student_id=student.id,
        branch_id=enrollment.batch.branch_id,
        amount=payload.amount,
        upi_reference=payload.upi_reference,
        paid_on=payload.paid_on,
        status=CLAIM_PENDING,
        submitted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(claim)
    db.flush()

    context = {
        "student_name": student.full_name,
        "course_name": enrollment.batch.course.name,
        "batch_name": enrollment.batch.name,
        "amount": f"{payload.amount:,.2f}",
        "upi_reference": payload.upi_reference,
        "branch_name": branch.name,
    }
    if student.email:
        try:
            status, detail = send_templated_email(
                db,
                key="payment_awaiting_verification",
                recipient=student.email,
                context=context,
                branch_id=claim.branch_id,
                category="payment_awaiting_verification",
                student_id=student.id,
                enrollment_id=enrollment.id,
                triggered_by_id=current_user.id,
                dry_run=payment_emails_are_dry_run(),
            )
            claim.receipt_email_status = status
            claim.receipt_email_detail = detail
        except (EmailTemplateError, MailDeliveryError) as error:
            claim.receipt_email_status = "failed"
            claim.receipt_email_detail = str(error)

    record_audit(
        db,
        current_user.id,
        "payment_claim_submitted",
        "payment_claim",
        claim.id,
        {
            "installment_id": installment.id,
            "amount": str(payload.amount),
            "upi_reference": payload.upi_reference,
        },
    )
    db.commit()
    return _claim_staff_row(_load_own_claim(db, claim.id, student))


@router.post(
    "/payment-claims/{claim_id}/cancel",
    response_model=PaymentClaimResponse,
)
def cancel_own_claim(
    claim_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> PaymentClaimResponse:
    student = _current_student(db, current_user)
    claim = _load_own_claim(db, claim_id, student)
    if claim.status != CLAIM_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Only pending claims can be cancelled (this claim is {claim.status})",
        )
    claim.status = CLAIM_CANCELLED
    record_audit(
        db,
        current_user.id,
        "payment_claim_cancelled",
        "payment_claim",
        claim.id,
        {"upi_reference": claim.upi_reference, "amount": str(claim.amount)},
    )
    db.commit()
    return _claim_staff_row(_load_own_claim(db, claim.id, student))


@router.get("/payments/{payment_id}/receipt.pdf")
def download_own_receipt(
    payment_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> Response:
    student = _current_student(db, current_user)
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
    if payment.installment.fee_plan.enrollment.student_id != student.id:
        raise HTTPException(status_code=403, detail="This receipt is not yours")
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
