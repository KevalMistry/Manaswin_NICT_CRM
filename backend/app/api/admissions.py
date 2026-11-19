from __future__ import annotations

import secrets
import shutil
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.core.ratelimit import rate_limit
from app.core.uploads import content_matches_extension
from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.core.config import GST_RATE_PERCENT
from app.models.admission import AdmissionApplication, AdmissionDocument, AdmissionPayment
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.fee import FeeInstallment, FeePlan
from app.models.student import Student
from app.models.student_document import StudentDocument
from app.models.user import User
from app.schemas.admission import (
    AdmissionApproveRequest,
    AdmissionApproveResponse,
    AdmissionCatalogBranch,
    AdmissionCatalogCourse,
    AdmissionCatalogResponse,
    AdmissionDetailResponse,
    AdmissionDocumentResponse,
    AdmissionInvoiceResponse,
    AdmissionPaymentCreate,
    AdmissionPaymentResponse,
    AdmissionRejectRequest,
    AdmissionResponse,
    AdmissionStatsResponse,
    AdmissionStatusUpdate,
    PublicAdmissionCreate,
    PublicAdmissionCreated,
    PublicAdmissionDocument,
    PublicAdmissionPayment,
    PublicAdmissionStatus,
    PublicPaymentIntentResponse,
    PublicPaymentVerifyRequest,
    PublicPaymentVerifyResponse,
)
from app.services.admission_payments import (
    PaymentGatewayError,
    create_razorpay_order,
    currency,
    gateway_configured,
    gst_breakdown,
    provider_name,
    razorpay_key_id,
    verify_razorpay_signature,
)


router = APIRouter(prefix="/api/admissions", tags=["Admissions"])
public_router = APIRouter(prefix="/api/public/admissions", tags=["Public Admissions"])

AdmissionsRead = require_roles("Super Admin", "Branch Admin", "Staff", "Counsellor")
AdmissionStaff = require_roles("Super Admin", "Branch Admin", "Staff")
AdmissionReviewer = require_roles("Super Admin", "Branch Admin")
AdmissionManager = require_roles("Super Admin", "Branch Admin", "Staff", "Counsellor")

BACKEND_DIR = Path(__file__).resolve().parents[2]
ADMISSION_UPLOAD_DIR = BACKEND_DIR / "private_uploads" / "admissions"
STUDENT_UPLOAD_DIR = BACKEND_DIR / "uploads" / "students"
DOCUMENT_TYPES = {
    "aadhaar": "Aadhaar Card",
    "pan": "PAN Card",
    "photo": "Photograph",
    "marksheet": "Marksheet",
    "certificate": "Certificate",
    "id_proof": "ID Proof",
    "other": "Other",
}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
}
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_application(db: DatabaseSession, application_id: int) -> AdmissionApplication:
    application = db.scalar(
        select(AdmissionApplication)
        .options(
            joinedload(AdmissionApplication.branch),
            joinedload(AdmissionApplication.course),
            joinedload(AdmissionApplication.batch),
            joinedload(AdmissionApplication.student),
            joinedload(AdmissionApplication.enrollment),
            joinedload(AdmissionApplication.reviewed_by),
            joinedload(AdmissionApplication.documents),
            joinedload(AdmissionApplication.payments).joinedload(AdmissionPayment.recorded_by),
        )
        .where(AdmissionApplication.id == application_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Admission application not found")
    return application


def _scoped_application(
    db: DatabaseSession, application_id: int, current_user: User
) -> AdmissionApplication:
    application = _load_application(db, application_id)
    check_branch_access(current_user, application.branch_id)
    return application


def _public_application(db: DatabaseSession, application_code: str) -> AdmissionApplication:
    application = db.scalar(
        select(AdmissionApplication)
        .options(
            joinedload(AdmissionApplication.branch),
            joinedload(AdmissionApplication.course),
            joinedload(AdmissionApplication.student),
            joinedload(AdmissionApplication.enrollment),
            joinedload(AdmissionApplication.documents),
            joinedload(AdmissionApplication.payments),
        )
        .where(AdmissionApplication.application_code == application_code)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Admission application not found")
    return application


def _check_token(application: AdmissionApplication, token: str) -> None:
    if not token or not secrets.compare_digest(application.upload_token, token):
        raise HTTPException(
            status_code=403,
            detail="The application code and access token do not match",
        )


def _paid_total(application: AdmissionApplication) -> Decimal:
    return sum(
        (payment.amount for payment in application.payments if payment.status == "paid"),
        Decimal("0.00"),
    )


def _refresh_payment_status(application: AdmissionApplication) -> None:
    paid = _paid_total(application)
    if paid <= 0:
        application.payment_status = "unpaid"
    elif application.registration_fee > 0 and paid < application.registration_fee:
        application.payment_status = "pending"
    else:
        application.payment_status = "paid"


def _document_response(
    application: AdmissionApplication, document: AdmissionDocument
) -> AdmissionDocumentResponse:
    return AdmissionDocumentResponse(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        file_name=document.file_name,
        content_type=document.content_type,
        file_size=document.file_size,
        uploaded_at=document.uploaded_at,
        download_url=f"/api/admissions/{application.id}/documents/{document.id}",
    )


def _public_document_response(
    application: AdmissionApplication, document: AdmissionDocument, token: str
) -> PublicAdmissionDocument:
    return PublicAdmissionDocument(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        file_name=document.file_name,
        content_type=document.content_type,
        file_size=document.file_size,
        uploaded_at=document.uploaded_at,
        download_url=(
            f"/api/public/admissions/{application.application_code}"
            f"/documents/{document.id}?token={token}"
        ),
    )


def _payment_response(payment: AdmissionPayment) -> AdmissionPaymentResponse:
    return AdmissionPaymentResponse(
        id=payment.id,
        invoice_number=payment.invoice_number,
        amount=payment.amount,
        taxable_amount=payment.taxable_amount,
        gst_amount=payment.gst_amount,
        payment_method=payment.payment_method,
        provider=payment.provider,
        status=payment.status,
        reference=payment.reference,
        provider_order_id=payment.provider_order_id,
        provider_payment_id=payment.provider_payment_id,
        paid_at=payment.paid_at,
        recorded_by=payment.recorded_by.full_name if payment.recorded_by else None,
        created_at=payment.created_at,
    )


def _application_response(application: AdmissionApplication) -> AdmissionResponse:
    return AdmissionResponse(
        id=application.id,
        application_code=application.application_code,
        full_name=application.full_name,
        email=application.email,
        phone=application.phone,
        date_of_birth=application.date_of_birth,
        gender=application.gender,
        parent_name=application.parent_name,
        parent_phone=application.parent_phone,
        address=application.address,
        qualification=application.qualification,
        notes=application.notes,
        branch_id=application.branch_id,
        branch_name=application.branch.name,
        course_id=application.course_id,
        course_name=application.course.name,
        batch_id=application.batch_id,
        batch_name=application.batch.name if application.batch else None,
        status=application.status,
        payment_status=application.payment_status,
        registration_fee=application.registration_fee,
        total_paid=_paid_total(application),
        documents_count=len(application.documents),
        source=application.source,
        review_notes=application.review_notes,
        rejection_reason=application.rejection_reason,
        reviewed_by=application.reviewed_by.full_name if application.reviewed_by else None,
        reviewed_at=application.reviewed_at,
        student_id=application.student_id,
        student_code=application.student.student_code if application.student else None,
        roll_number=application.student.roll_number if application.student else None,
        enrollment_id=application.enrollment_id,
        enrollment_code=application.enrollment.enrollment_code if application.enrollment else None,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def _application_detail(application: AdmissionApplication) -> AdmissionDetailResponse:
    base = _application_response(application).model_dump()
    return AdmissionDetailResponse(
        **base,
        documents=[
            _document_response(application, document)
            for document in sorted(application.documents, key=lambda item: item.id)
        ],
        payments=[
            _payment_response(payment)
            for payment in sorted(
                application.payments, key=lambda item: item.created_at, reverse=True
            )
        ],
    )


def _generate_application_code(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(8):
        candidate = f"ADM-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(
            select(AdmissionApplication.id).where(
                AdmissionApplication.application_code == candidate
            )
        ) is None:
            return candidate
    raise HTTPException(
        status_code=503, detail="Could not generate a unique application code"
    )


def _generate_student_code(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(8):
        candidate = f"STU-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(select(Student.id).where(Student.student_code == candidate)) is None:
            return candidate
    raise HTTPException(status_code=503, detail="Could not generate a unique student ID")


def _generate_roll_number(db: DatabaseSession, branch: Branch) -> str:
    year = datetime.now().year
    prefix = f"{branch.code.upper()}-{year}-"
    for sequence in range(1, 10000):
        candidate = f"{prefix}{sequence:04d}"
        if db.scalar(select(Student.id).where(Student.roll_number == candidate)) is None:
            return candidate
    raise HTTPException(status_code=503, detail="Could not generate a unique roll number")


def _generate_enrollment_code(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(8):
        candidate = f"ENR-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(
            select(Enrollment.id).where(Enrollment.enrollment_code == candidate)
        ) is None:
            return candidate
    raise HTTPException(
        status_code=503, detail="Could not generate a unique enrollment code"
    )


def _generate_invoice_number(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(8):
        candidate = f"INV-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(
            select(AdmissionPayment.id).where(
                AdmissionPayment.invoice_number == candidate
            )
        ) is None:
            return candidate
    raise HTTPException(status_code=503, detail="Could not generate a unique invoice number")


def _save_document(
    db: DatabaseSession,
    application: AdmissionApplication,
    *,
    file: UploadFile,
    document_type: str,
    title: str,
    actor_id: int | None,
) -> AdmissionDocument:
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Choose a valid document type")

    original_name = Path(file.filename or "document").name
    extension = Path(original_name).suffix.lower()
    if extension not in DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Document must be a PDF, image, Word, Excel or ZIP file",
        )
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded document is empty")
    if len(data) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=400, detail="The document must be 10 MB or smaller"
        )
    if not content_matches_extension(extension, data):
        raise HTTPException(
            status_code=400,
            detail="The file content does not match its type. Upload a genuine file.",
        )

    directory = ADMISSION_UPLOAD_DIR / str(application.id)
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{document_type}-{uuid4().hex}{extension}"
    (directory / stored_name).write_bytes(data)

    document = AdmissionDocument(
        application_id=application.id,
        document_type=document_type,
        title=title.strip() or DOCUMENT_TYPES[document_type],
        file_name=original_name,
        file_key=f"{application.id}/{stored_name}",
        content_type=file.content_type,
        file_size=len(data),
    )
    db.add(document)
    record_audit(
        db,
        actor_id,
        "admission_document_uploaded",
        "admission",
        application.id,
        {"document_type": document_type, "file": original_name},
    )
    db.flush()
    return document


def _document_path(document: AdmissionDocument) -> Path:
    root = ADMISSION_UPLOAD_DIR.resolve()
    path = (ADMISSION_UPLOAD_DIR / document.file_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")
    return path


def _copy_documents_to_student(
    db: DatabaseSession,
    application: AdmissionApplication,
    student: Student,
    actor_id: int,
) -> None:
    for document in application.documents:
        try:
            source = _document_path(document)
        except HTTPException:
            continue
        destination_dir = STUDENT_UPLOAD_DIR / str(student.id) / "documents"
        destination_dir.mkdir(parents=True, exist_ok=True)
        extension = Path(document.file_name).suffix.lower()
        stored_name = f"{document.document_type}-{uuid4().hex}{extension}"
        shutil.copyfile(source, destination_dir / stored_name)
        if document.document_type == "photo":
            photo_dir = STUDENT_UPLOAD_DIR / str(student.id)
            photo_name = f"photo-{uuid4().hex}{extension}"
            shutil.copyfile(source, photo_dir / photo_name)
            student.photo_url = f"/uploads/students/{student.id}/{photo_name}"
        db.add(
            StudentDocument(
                student_id=student.id,
                document_type=document.document_type,
                title=document.title,
                file_name=document.file_name,
                file_url=f"/uploads/students/{student.id}/documents/{stored_name}",
                content_type=document.content_type,
                file_size=document.file_size,
                uploaded_by_id=actor_id,
            )
        )


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AdmissionResponse])
def list_admissions(
    db: DatabaseSession,
    current_user: User = Depends(AdmissionsRead),
    status_filter: str | None = Query(default=None, alias="status"),
    payment_status: str | None = Query(default=None),
    branch_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[AdmissionResponse]:
    query = (
        select(AdmissionApplication)
        .options(
            joinedload(AdmissionApplication.branch),
            joinedload(AdmissionApplication.course),
            joinedload(AdmissionApplication.batch),
            joinedload(AdmissionApplication.student),
            joinedload(AdmissionApplication.enrollment),
            joinedload(AdmissionApplication.reviewed_by),
            joinedload(AdmissionApplication.documents),
            joinedload(AdmissionApplication.payments),
        )
        .order_by(AdmissionApplication.created_at.desc())
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(AdmissionApplication.branch_id == scope)
    elif branch_id is not None:
        query = query.where(AdmissionApplication.branch_id == branch_id)
    if status_filter:
        query = query.where(AdmissionApplication.status == status_filter)
    if payment_status:
        query = query.where(AdmissionApplication.payment_status == payment_status)
    if search:
        needle = f"%{search.strip()}%"
        query = query.where(
            or_(
                AdmissionApplication.full_name.ilike(needle),
                AdmissionApplication.application_code.ilike(needle),
                AdmissionApplication.email.ilike(needle),
                AdmissionApplication.phone.ilike(needle),
            )
        )
    applications = list(db.scalars(query.offset(offset).limit(limit)).unique().all())
    return [_application_response(application) for application in applications]


@router.get("/stats", response_model=AdmissionStatsResponse)
def admission_stats(
    db: DatabaseSession,
    current_user: User = Depends(AdmissionsRead),
) -> AdmissionStatsResponse:
    scope = branch_scope(current_user)
    base = select(AdmissionApplication)
    if scope is not None:
        base = base.where(AdmissionApplication.branch_id == scope)
    applications = list(db.scalars(base).all())
    paid_query = (
        select(AdmissionPayment)
        .join(AdmissionPayment.application)
        .where(AdmissionPayment.status == "paid")
    )
    if scope is not None:
        paid_query = paid_query.where(AdmissionApplication.branch_id == scope)
    paid_rows = db.scalars(paid_query).all()
    fees_collected = sum(
        (payment.amount for payment in paid_rows), Decimal("0.00")
    )
    return AdmissionStatsResponse(
        total=len(applications),
        submitted=sum(1 for item in applications if item.status == "submitted"),
        under_review=sum(1 for item in applications if item.status == "under_review"),
        enrolled=sum(1 for item in applications if item.status == "enrolled"),
        rejected=sum(1 for item in applications if item.status == "rejected"),
        withdrawn=sum(1 for item in applications if item.status == "withdrawn"),
        unpaid=sum(1 for item in applications if item.payment_status == "unpaid"),
        pending_payment=sum(
            1 for item in applications if item.payment_status == "pending"
        ),
        paid=sum(1 for item in applications if item.payment_status == "paid"),
        fees_collected=fees_collected,
    )


@router.get("/{application_id}", response_model=AdmissionDetailResponse)
def get_admission(
    application_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionsRead),
) -> AdmissionDetailResponse:
    return _application_detail(_scoped_application(db, application_id, current_user))


@router.patch(
    "/{application_id}/status",
    response_model=AdmissionDetailResponse,
    dependencies=[Depends(AdmissionsRead)],
)
def update_admission_status(
    application_id: int,
    payload: AdmissionStatusUpdate,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionManager),
) -> AdmissionDetailResponse:
    application = _scoped_application(db, application_id, current_user)
    if application.status == "enrolled":
        raise HTTPException(
            status_code=400,
            detail="This application is already enrolled and cannot change status",
        )
    if payload.status == "rejected" and not (payload.rejection_reason or payload.notes):
        raise HTTPException(
            status_code=400, detail="Add a reason when rejecting an application"
        )
    application.status = payload.status
    if payload.notes:
        application.review_notes = payload.notes
    if payload.status == "rejected":
        application.rejection_reason = payload.rejection_reason or payload.notes
    if payload.status in {"under_review", "rejected"}:
        application.reviewed_by_id = current_user.id
        application.reviewed_at = datetime.now()
    record_audit(
        db,
        current_user.id,
        "admission_status_updated",
        "admission",
        application.id,
        {"status": payload.status},
    )
    db.commit()
    return _application_detail(_load_application(db, application.id))


@router.post(
    "/{application_id}/reject",
    response_model=AdmissionDetailResponse,
    dependencies=[Depends(AdmissionsRead)],
)
def reject_admission(
    application_id: int,
    payload: AdmissionRejectRequest,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionReviewer),
) -> AdmissionDetailResponse:
    application = _scoped_application(db, application_id, current_user)
    if application.status == "enrolled":
        raise HTTPException(
            status_code=400, detail="An enrolled application cannot be rejected"
        )
    application.status = "rejected"
    application.rejection_reason = payload.reason
    application.reviewed_by_id = current_user.id
    application.reviewed_at = datetime.now()
    record_audit(
        db,
        current_user.id,
        "admission_rejected",
        "admission",
        application.id,
        {"reason": payload.reason},
    )
    db.commit()
    return _application_detail(_load_application(db, application.id))


@router.post(
    "/{application_id}/approve",
    response_model=AdmissionApproveResponse,
    dependencies=[Depends(AdmissionsRead)],
)
def approve_admission(
    application_id: int,
    payload: AdmissionApproveRequest,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionStaff),
) -> AdmissionApproveResponse:
    application = _scoped_application(db, application_id, current_user)
    if application.status == "enrolled" or application.student_id is not None:
        raise HTTPException(
            status_code=409, detail="This application has already been enrolled"
        )
    if application.status in {"rejected", "withdrawn"}:
        raise HTTPException(
            status_code=400,
            detail="Rejected or withdrawn applications cannot be approved",
        )
    if (
        application.registration_fee > 0
        and application.payment_status != "paid"
        and not payload.override_unpaid_fee
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "The registration fee is not paid. Record the payment or set "
                "override_unpaid_fee to enrol anyway."
            ),
        )
    if payload.override_unpaid_fee and current_user.role.name not in {
        "Super Admin",
        "Branch Admin",
    }:
        raise HTTPException(
            status_code=403,
            detail="Only an administrator can override an unpaid registration fee",
        )

    batch = db.get(Batch, payload.batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.course_id != application.course_id:
        raise HTTPException(
            status_code=400, detail="The batch does not belong to the applied course"
        )
    if batch.branch_id != application.branch_id:
        raise HTTPException(
            status_code=400, detail="The batch does not belong to the applied branch"
        )
    active_enrollments = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.batch_id == batch.id,
            Enrollment.status == "active",
        )
    ) or 0
    if active_enrollments >= batch.capacity:
        raise HTTPException(
            status_code=400, detail="This batch is already at full capacity"
        )

    branch = db.get(Branch, application.branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")

    admission_date = date.today()
    student = Student(
        student_code=_generate_student_code(db),
        roll_number=_generate_roll_number(db, branch),
        full_name=application.full_name,
        email=application.email,
        phone=application.phone,
        date_of_birth=application.date_of_birth,
        gender=application.gender,
        parent_name=application.parent_name,
        parent_phone=application.parent_phone,
        address=application.address,
        qualification=application.qualification,
        branch_id=application.branch_id,
        is_active=True,
    )
    db.add(student)
    db.flush()

    _copy_documents_to_student(db, application, student, current_user.id)

    enrollment = Enrollment(
        enrollment_code=_generate_enrollment_code(db),
        student_id=student.id,
        batch_id=batch.id,
        admission_date=admission_date,
        status="active",
    )
    db.add(enrollment)
    db.flush()

    fee_plan_id: int | None = None
    course_fee = application.course.fee_amount
    if course_fee is not None and course_fee > 0:
        if payload.discount_amount > course_fee:
            raise HTTPException(
                status_code=400,
                detail="The discount cannot be greater than the course fee",
            )
        net_amount = (course_fee - payload.discount_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if net_amount > 0:
            fee_plan = FeePlan(
                enrollment_id=enrollment.id,
                total_amount=course_fee,
                discount_amount=payload.discount_amount,
                scholarship_amount=Decimal("0.00"),
            )
            db.add(fee_plan)
            db.flush()
            db.add(
                FeeInstallment(
                    fee_plan_id=fee_plan.id,
                    installment_number=1,
                    amount=net_amount,
                    due_date=admission_date,
                    status="pending",
                )
            )
            fee_plan_id = fee_plan.id
    elif payload.discount_amount > 0:
        raise HTTPException(
            status_code=400,
            detail="This course has no course fee to discount",
        )

    application.status = "enrolled"
    application.batch_id = batch.id
    application.student_id = student.id
    application.enrollment_id = enrollment.id
    application.reviewed_by_id = current_user.id
    application.reviewed_at = datetime.now()
    if payload.notes:
        application.review_notes = payload.notes
    record_audit(
        db,
        current_user.id,
        "admission_approved",
        "admission",
        application.id,
        {
            "student_id": student.id,
            "student_code": student.student_code,
            "roll_number": student.roll_number,
            "enrollment_id": enrollment.id,
            "batch_id": batch.id,
            "override_unpaid_fee": payload.override_unpaid_fee,
        },
    )
    db.commit()

    fresh = _load_application(db, application.id)
    return AdmissionApproveResponse(
        application=_application_detail(fresh),
        student_id=student.id,
        student_code=student.student_code,
        roll_number=student.roll_number or "",
        enrollment_id=enrollment.id,
        enrollment_code=enrollment.enrollment_code,
        fee_plan_id=fee_plan_id,
    )


@router.post(
    "/{application_id}/payments",
    response_model=AdmissionPaymentResponse,
    dependencies=[Depends(AdmissionsRead)],
)
def record_admission_payment(
    application_id: int,
    payload: AdmissionPaymentCreate,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionStaff),
) -> AdmissionPaymentResponse:
    application = _scoped_application(db, application_id, current_user)
    if application.status in {"rejected", "withdrawn"}:
        raise HTTPException(
            status_code=400,
            detail="Payments cannot be recorded for a closed application",
        )
    if application.registration_fee <= 0:
        raise HTTPException(
            status_code=400,
            detail="This course does not have a registration fee to collect",
        )
    amount = (
        payload.amount
        if payload.amount is not None
        else application.registration_fee
    )
    if amount is None or amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="This course does not have a registration fee to collect",
        )
    outstanding = application.registration_fee - _paid_total(application)
    if outstanding <= 0:
        raise HTTPException(
            status_code=409,
            detail="The registration fee has already been paid",
        )
    if amount > outstanding:
        raise HTTPException(
            status_code=400,
            detail=f"Payment exceeds the outstanding registration fee of {outstanding}",
        )

    existing_pending = db.scalar(
        select(AdmissionPayment)
        .where(
            AdmissionPayment.application_id == application.id,
            AdmissionPayment.status == "pending",
            AdmissionPayment.provider == "manual",
            AdmissionPayment.amount == amount,
        )
        .order_by(AdmissionPayment.created_at.desc())
    )
    taxable, gst = gst_breakdown(amount)
    payment = existing_pending or AdmissionPayment(
        application_id=application.id,
        amount=amount,
    )
    payment.amount = amount
    payment.taxable_amount = taxable
    payment.gst_amount = gst
    payment.payment_method = (payload.payment_method or "cash").strip().lower()[:30]
    payment.provider = "manual"
    payment.status = "paid"
    payment.reference = payload.reference
    payment.invoice_number = payment.invoice_number or _generate_invoice_number(db)
    payment.paid_at = (
        datetime.combine(payload.payment_date, time(12, 0))
        if payload.payment_date is not None
        else datetime.now()
    )
    payment.recorded_by_id = current_user.id
    if existing_pending is None:
        db.add(payment)

    db.flush()
    db.refresh(application)
    _refresh_payment_status(application)
    record_audit(
        db,
        current_user.id,
        "admission_payment_recorded",
        "admission",
        application.id,
        {
            "payment_id": payment.id,
            "invoice_number": payment.invoice_number,
            "amount": str(payment.amount),
            "method": payment.payment_method,
        },
    )
    db.commit()
    db.refresh(payment)
    return _payment_response(payment)


@router.get("/{application_id}/invoice", response_model=AdmissionInvoiceResponse)
def admission_invoice(
    application_id: int,
    db: DatabaseSession,
    payment_id: int | None = Query(default=None),
    current_user: User = Depends(AdmissionsRead),
) -> AdmissionInvoiceResponse:
    application = _scoped_application(db, application_id, current_user)
    payment: AdmissionPayment | None = None
    if payment_id is not None:
        payment = db.scalar(
            select(AdmissionPayment).where(
                AdmissionPayment.id == payment_id,
                AdmissionPayment.application_id == application.id,
                AdmissionPayment.status == "paid",
            )
        )
    else:
        payment = db.scalar(
            select(AdmissionPayment)
            .where(
                AdmissionPayment.application_id == application.id,
                AdmissionPayment.status == "paid",
                AdmissionPayment.invoice_number.is_not(None),
            )
            .order_by(AdmissionPayment.paid_at.desc())
        )
    if payment is None or payment.invoice_number is None:
        raise HTTPException(status_code=404, detail="No paid invoice found")
    branch = application.branch
    return AdmissionInvoiceResponse(
        invoice_number=payment.invoice_number,
        invoice_date=(payment.paid_at or payment.created_at).date(),
        application_code=application.application_code,
        applicant_name=application.full_name,
        student_code=application.student.student_code if application.student else None,
        roll_number=application.student.roll_number if application.student else None,
        course_name=application.course.name,
        branch_name=branch.name,
        branch_address=branch.address,
        branch_phone=branch.phone,
        branch_email=branch.email,
        branch_gstin=branch.gstin,
        amount=payment.amount,
        taxable_amount=payment.taxable_amount,
        gst_rate_percent=GST_RATE_PERCENT,
        gst_amount=payment.gst_amount,
        payment_method=payment.payment_method,
        reference=payment.reference,
        status=payment.status,
        paid_at=payment.paid_at,
    )


@router.get("/{application_id}/documents/{document_id}")
def download_admission_document(
    application_id: int,
    document_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AdmissionsRead),
) -> FileResponse:
    application = _scoped_application(db, application_id, current_user)
    document = db.scalar(
        select(AdmissionDocument).where(
            AdmissionDocument.id == document_id,
            AdmissionDocument.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        _document_path(document),
        media_type=document.content_type or "application/octet-stream",
        filename=document.file_name,
    )


@router.post(
    "/{application_id}/documents",
    response_model=AdmissionDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(AdmissionsRead)],
)
async def upload_admission_document(
    application_id: int,
    db: DatabaseSession,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    title: str = Form(default=""),
    current_user: User = Depends(AdmissionManager),
) -> AdmissionDocumentResponse:
    application = _scoped_application(db, application_id, current_user)
    document = _save_document(
        db,
        application,
        file=file,
        document_type=document_type,
        title=title,
        actor_id=current_user.id,
    )
    db.commit()
    db.refresh(document)
    return _document_response(application, document)


# ---------------------------------------------------------------------------
# Public API (no authentication)
# ---------------------------------------------------------------------------


@public_router.get("/catalog", response_model=AdmissionCatalogResponse)
def public_admission_catalog(db: DatabaseSession) -> AdmissionCatalogResponse:
    branches = list(
        db.scalars(
            select(Branch)
            .where(Branch.is_active.is_(True))
            .order_by(Branch.name)
        ).all()
    )
    courses = list(
        db.scalars(
            select(Course).where(Course.is_active.is_(True)).order_by(Course.name)
        ).all()
    )
    return AdmissionCatalogResponse(
        branches=[
            AdmissionCatalogBranch(
                id=branch.id,
                name=branch.name,
                code=branch.code,
                address=branch.address,
                phone=branch.phone,
                email=branch.email,
                gstin=branch.gstin,
            )
            for branch in branches
        ],
        courses=[
            AdmissionCatalogCourse(
                id=course.id,
                name=course.name,
                code=course.code,
                duration_months=course.duration_months,
                fee_amount=course.fee_amount,
                registration_fee=course.registration_fee,
            )
            for course in courses
        ],
        payment_provider=provider_name(),
        payment_currency=currency(),
        gst_rate_percent=GST_RATE_PERCENT,
    )


@public_router.post(
    "",
    response_model=PublicAdmissionCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("admission_submit", 8, 3600))],
)
def submit_public_admission(
    payload: PublicAdmissionCreate,
    db: DatabaseSession,
) -> PublicAdmissionCreated:
    branch = db.get(Branch, payload.branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=400, detail="Choose an active branch")
    course = db.get(Course, payload.course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=400, detail="Choose an active course")

    application = AdmissionApplication(
        application_code=_generate_application_code(db),
        full_name=payload.full_name.strip(),
        email=str(payload.email) if payload.email else None,
        phone=payload.phone.strip(),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        parent_name=payload.parent_name,
        parent_phone=payload.parent_phone,
        address=payload.address,
        qualification=payload.qualification,
        notes=payload.notes,
        branch_id=branch.id,
        course_id=course.id,
        status="submitted",
        payment_status="unpaid",
        registration_fee=course.registration_fee,
        source="online",
        upload_token=secrets.token_urlsafe(32),
    )
    db.add(application)
    db.flush()
    record_audit(
        db,
        None,
        "admission_submitted",
        "admission",
        application.id,
        {
            "application_code": application.application_code,
            "branch_id": branch.id,
            "course_id": course.id,
        },
    )
    db.commit()
    db.refresh(application)
    return PublicAdmissionCreated(
        application_id=application.id,
        application_code=application.application_code,
        upload_token=application.upload_token,
        status=application.status,
        payment_status=application.payment_status,
        registration_fee=application.registration_fee,
        course_name=course.name,
        branch_name=branch.name,
        message=(
            "Application received. Keep the application code and access token "
            "safe so you can upload documents and track the outcome."
        ),
    )


@public_router.get(
    "/{application_code}",
    response_model=PublicAdmissionStatus,
)
def get_public_admission(
    application_code: str,
    db: DatabaseSession,
    token: str = Query(min_length=10, max_length=100),
) -> PublicAdmissionStatus:
    application = _public_application(db, application_code)
    _check_token(application, token)
    return PublicAdmissionStatus(
        application_code=application.application_code,
        full_name=application.full_name,
        email=application.email,
        phone=application.phone,
        branch_name=application.branch.name,
        course_name=application.course.name,
        status=application.status,
        payment_status=application.payment_status,
        registration_fee=application.registration_fee,
        total_paid=_paid_total(application),
        documents=[
            _public_document_response(application, document, token)
            for document in sorted(application.documents, key=lambda item: item.id)
        ],
        payments=[
            PublicAdmissionPayment(
                amount=payment.amount,
                status=payment.status,
                payment_method=payment.payment_method,
                provider=payment.provider,
                reference=payment.reference,
                invoice_number=payment.invoice_number,
                paid_at=payment.paid_at,
                created_at=payment.created_at,
            )
            for payment in sorted(
                application.payments, key=lambda item: item.created_at, reverse=True
            )
        ],
        student_code=application.student.student_code if application.student else None,
        roll_number=application.student.roll_number if application.student else None,
        enrollment_code=(
            application.enrollment.enrollment_code if application.enrollment else None
        ),
        rejection_reason=application.rejection_reason,
        created_at=application.created_at,
    )


@public_router.post(
    "/{application_code}/documents",
    response_model=PublicAdmissionDocument,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("admission_upload", 40, 3600))],
)
async def upload_public_admission_document(
    application_code: str,
    db: DatabaseSession,
    token: str = Query(min_length=10, max_length=100),
    file: UploadFile = File(...),
    document_type: str = Form(...),
    title: str = Form(default=""),
) -> PublicAdmissionDocument:
    application = _public_application(db, application_code)
    _check_token(application, token)
    if application.status not in {"submitted", "under_review"}:
        raise HTTPException(
            status_code=400,
            detail="Documents can no longer be uploaded for this application",
        )
    document = _save_document(
        db,
        application,
        file=file,
        document_type=document_type,
        title=title,
        actor_id=None,
    )
    db.commit()
    db.refresh(document)
    return _public_document_response(application, document, token)


@public_router.get("/{application_code}/documents/{document_id}")
def download_public_admission_document(
    application_code: str,
    document_id: int,
    db: DatabaseSession,
    token: str = Query(min_length=10, max_length=100),
) -> FileResponse:
    application = _public_application(db, application_code)
    _check_token(application, token)
    document = db.scalar(
        select(AdmissionDocument).where(
            AdmissionDocument.id == document_id,
            AdmissionDocument.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        _document_path(document),
        media_type=document.content_type or "application/octet-stream",
        filename=document.file_name,
    )


@public_router.post(
    "/{application_code}/payment-intent",
    response_model=PublicPaymentIntentResponse,
)
def create_public_payment_intent(
    application_code: str,
    db: DatabaseSession,
    token: str = Query(min_length=10, max_length=100),
) -> PublicPaymentIntentResponse:
    application = _public_application(db, application_code)
    _check_token(application, token)
    if application.status in {"rejected", "withdrawn"}:
        raise HTTPException(
            status_code=400,
            detail="Payments cannot be made for a closed application",
        )
    if application.payment_status == "paid":
        raise HTTPException(
            status_code=409, detail="The registration fee has already been paid"
        )
    if application.registration_fee <= 0:
        raise HTTPException(
            status_code=400, detail="This course does not have a registration fee"
        )

    provider = provider_name()
    if provider == "manual":
        pending = db.scalar(
            select(AdmissionPayment)
            .where(
                AdmissionPayment.application_id == application.id,
                AdmissionPayment.provider == "manual",
                AdmissionPayment.status == "pending",
            )
            .order_by(AdmissionPayment.created_at.desc())
        )
        if pending is None:
            pending = AdmissionPayment(
                application_id=application.id,
                amount=application.registration_fee,
                payment_method="manual",
                provider="manual",
                status="pending",
            )
            db.add(pending)
        application.payment_status = "pending"
        record_audit(
            db,
            None,
            "admission_payment_initiated",
            "admission",
            application.id,
            {"provider": "manual", "amount": str(application.registration_fee)},
        )
        db.commit()
        return PublicPaymentIntentResponse(
            application_code=application.application_code,
            provider="manual",
            status="pending",
            payment_status=application.payment_status,
            amount=application.registration_fee,
            currency=currency(),
            order_id=None,
            key_id=None,
            instructions=(
                "Please pay the registration fee at the admissions desk. Once "
                "the institute records the payment, your application will show "
                "as paid and the invoice will be available."
            ),
        )

    if not gateway_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Online payment is not configured. Pay the registration fee at "
                "the branch and the institute will record it manually."
            ),
        )
    pending = db.scalar(
        select(AdmissionPayment)
        .where(
            AdmissionPayment.application_id == application.id,
            AdmissionPayment.provider == "razorpay",
            AdmissionPayment.status == "pending",
            AdmissionPayment.provider_order_id.is_not(None),
        )
        .order_by(AdmissionPayment.created_at.desc())
    )
    if pending is not None and pending.provider_order_id:
        # Reuse the open order instead of creating a new one every time the
        # applicant refreshes the payment page.
        order_id = pending.provider_order_id
    else:
        try:
            order = create_razorpay_order(
                application.registration_fee,
                application.application_code,
                {
                    "application_code": application.application_code,
                    "course": application.course.name,
                },
            )
        except PaymentGatewayError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        order_id = str(order.get("id") or "")
        if not order_id:
            raise HTTPException(
                status_code=502, detail="The payment gateway did not return an order id"
            )
        db.add(
            AdmissionPayment(
                application_id=application.id,
                amount=application.registration_fee,
                payment_method="online",
                provider="razorpay",
                status="pending",
                provider_order_id=order_id,
            )
        )
        record_audit(
            db,
            None,
            "admission_payment_initiated",
            "admission",
            application.id,
            {"provider": "razorpay", "order_id": order_id},
        )

    application.payment_status = "pending"
    db.commit()
    return PublicPaymentIntentResponse(
        application_code=application.application_code,
        provider="razorpay",
        status="pending",
        payment_status=application.payment_status,
        amount=application.registration_fee,
        currency=currency(),
        order_id=order_id,
        key_id=razorpay_key_id(),
        instructions="Complete the payment in the secure Razorpay checkout.",
    )


@public_router.post(
    "/{application_code}/payment/verify",
    response_model=PublicPaymentVerifyResponse,
    dependencies=[Depends(rate_limit("admission_pay_verify", 20, 600))],
)
def verify_public_payment(
    application_code: str,
    payload: PublicPaymentVerifyRequest,
    db: DatabaseSession,
    token: str = Query(min_length=10, max_length=100),
) -> PublicPaymentVerifyResponse:
    application = _public_application(db, application_code)
    _check_token(application, token)
    payment = db.scalar(
        select(AdmissionPayment).where(
            AdmissionPayment.application_id == application.id,
            AdmissionPayment.provider == "razorpay",
            AdmissionPayment.provider_order_id == payload.order_id,
            AdmissionPayment.status == "pending",
        )
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Pending payment not found")
    if not verify_razorpay_signature(
        payload.order_id, payload.payment_id, payload.signature
    ):
        raise HTTPException(
            status_code=400, detail="Payment signature verification failed"
        )
    taxable, gst = gst_breakdown(payment.amount)
    payment.taxable_amount = taxable
    payment.gst_amount = gst
    payment.status = "paid"
    payment.payment_method = "online"
    payment.provider_payment_id = payload.payment_id
    payment.paid_at = datetime.now()
    payment.invoice_number = payment.invoice_number or _generate_invoice_number(db)
    db.flush()
    db.refresh(application)
    _refresh_payment_status(application)
    record_audit(
        db,
        None,
        "admission_payment_verified",
        "admission",
        application.id,
        {
            "payment_id": payment.id,
            "order_id": payload.order_id,
            "invoice_number": payment.invoice_number,
        },
    )
    db.commit()
    return PublicPaymentVerifyResponse(
        application_code=application.application_code,
        payment_status=application.payment_status,
        invoice_number=payment.invoice_number,
        message="Payment verified. Your registration fee is now marked as paid.",
    )
