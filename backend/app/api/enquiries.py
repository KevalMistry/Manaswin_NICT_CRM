from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.api.students import _generate_student_code
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.role import Role
from app.models.student import Student
from app.models.user import User
from app.schemas.enquiry import (
    ENQUIRY_SOURCES,
    ENQUIRY_STATUSES,
    EnquiryConvertRequest,
    EnquiryConvertResponse,
    EnquiryCreate,
    EnquiryResponse,
    EnquiryUpdate,
)
from app.schemas.enrollment import EnrollmentResponse
from app.schemas.student import StudentResponse


router = APIRouter(prefix="/api/enquiries", tags=["Enquiries"])
EnquiryUser = require_roles("Super Admin", "Branch Admin", "Counsellor")
EnquiriesRead = require_module("enquiries")
EnquiriesWrite = require_module("enquiries")


def _generate_enquiry_code(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(5):
        candidate = f"ENQ-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(select(Enquiry.id).where(Enquiry.enquiry_code == candidate)) is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not generate a unique enquiry ID",
    )


def _validate_branch(db: DatabaseSession, current_user: User, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=400, detail="Active branch does not exist")
    check_branch_access(current_user, branch_id)
    return branch


def _validate_course(db: DatabaseSession, course_id: int | None) -> None:
    if course_id is None:
        return
    course = db.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=400, detail="Active course does not exist")


def _validate_counsellor(
    db: DatabaseSession, counsellor_id: int | None, branch_id: int
) -> None:
    if counsellor_id is None:
        return
    counsellor = db.get(User, counsellor_id)
    if (
        counsellor is None
        or not counsellor.is_active
        or counsellor.role.name != "Counsellor"
        or counsellor.branch_id != branch_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Counsellor must be an active Counsellor assigned to the enquiry branch",
        )


@router.get("", response_model=list[EnquiryResponse], dependencies=[Depends(EnquiriesRead)])
def list_enquiries(
    db: DatabaseSession,
    current_user: User = Depends(EnquiryUser),
    branch_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    follow_up_before: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[Enquiry]:
    check_branch_access(current_user, branch_id)
    scope = branch_scope(current_user)
    if scope is not None:
        branch_id = scope

    if status_filter is not None and status_filter not in ENQUIRY_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown enquiry status")
    if source is not None and source not in ENQUIRY_SOURCES:
        raise HTTPException(status_code=400, detail="Unknown enquiry source")

    query = select(Enquiry)
    if branch_id is not None:
        query = query.where(Enquiry.branch_id == branch_id)
    if status_filter is not None:
        query = query.where(Enquiry.status == status_filter)
    if source is not None:
        query = query.where(Enquiry.source == source)
    if follow_up_before is not None:
        try:
            cutoff = datetime.strptime(follow_up_before, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="follow_up_before must be a YYYY-MM-DD date"
            ) from None
        query = query.where(
            Enquiry.follow_up_date.is_not(None), Enquiry.follow_up_date <= cutoff
        )
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Enquiry.full_name.ilike(pattern),
                Enquiry.phone.ilike(pattern),
                Enquiry.email.ilike(pattern),
                Enquiry.enquiry_code.ilike(pattern),
            )
        )
    return list(
        db.scalars(
            query.order_by(Enquiry.created_at.desc()).offset(offset).limit(limit)
        ).all()
    )


@router.get("/{enquiry_id}", response_model=EnquiryResponse, dependencies=[Depends(EnquiriesRead)])
def get_enquiry(
    enquiry_id: int,
    db: DatabaseSession,
    current_user: User = Depends(EnquiryUser),
) -> Enquiry:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    check_branch_access(current_user, enquiry.branch_id)
    return enquiry


@router.post(
    "",
    response_model=EnquiryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(EnquiriesWrite)],
)
def create_enquiry(
    payload: EnquiryCreate,
    db: DatabaseSession,
    current_user: User = Depends(EnquiryUser),
) -> Enquiry:
    _validate_branch(db, current_user, payload.branch_id)
    _validate_course(db, payload.course_id)
    counsellor_id = payload.counsellor_id
    if current_user.role.name == "Counsellor":
        counsellor_id = current_user.id
    else:
        _validate_counsellor(db, counsellor_id, payload.branch_id)

    enquiry = Enquiry(
        enquiry_code=_generate_enquiry_code(db),
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        branch_id=payload.branch_id,
        course_id=payload.course_id,
        source=payload.source,
        status="new_lead",
        notes=payload.notes,
        follow_up_date=payload.follow_up_date,
        counsellor_id=counsellor_id,
    )
    db.add(enquiry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create enquiry") from None
    db.refresh(enquiry)
    return enquiry


@router.patch(
    "/{enquiry_id}",
    response_model=EnquiryResponse,
    dependencies=[Depends(EnquiriesWrite)],
)
def update_enquiry(
    enquiry_id: int,
    payload: EnquiryUpdate,
    db: DatabaseSession,
    current_user: User = Depends(EnquiryUser),
) -> Enquiry:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    check_branch_access(current_user, enquiry.branch_id)
    if enquiry.status == "admitted":
        raise HTTPException(
            status_code=409,
            detail="An admitted enquiry is locked. Update the student or enrollment instead.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "branch_id" in changes:
        _validate_branch(db, current_user, changes["branch_id"])
    if "course_id" in changes:
        _validate_course(db, changes["course_id"])
    if "counsellor_id" in changes:
        target_branch = changes.get("branch_id", enquiry.branch_id)
        _validate_counsellor(db, changes["counsellor_id"], target_branch)

    for field, value in changes.items():
        setattr(enquiry, field, str(value) if field == "email" and value else value)
    if "status" in changes and changes["status"] == "lost":
        enquiry.follow_up_date = None

    db.commit()
    db.refresh(enquiry)
    return enquiry


@router.post(
    "/{enquiry_id}/convert",
    response_model=EnquiryConvertResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(EnquiriesWrite)],
)
def convert_enquiry(
    enquiry_id: int,
    payload: EnquiryConvertRequest,
    db: DatabaseSession,
    current_user: User = Depends(EnquiryUser),
) -> EnquiryConvertResponse:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    check_branch_access(current_user, enquiry.branch_id)
    if enquiry.status == "admitted" or enquiry.student_id is not None:
        raise HTTPException(status_code=409, detail="Enquiry has already been admitted")
    if enquiry.status == "lost":
        raise HTTPException(status_code=409, detail="A lost enquiry cannot be admitted")

    batch = db.get(Batch, payload.batch_id)
    if batch is None or not batch.is_active:
        raise HTTPException(status_code=400, detail="Active batch does not exist")
    if batch.branch_id != enquiry.branch_id:
        raise HTTPException(
            status_code=400, detail="Batch and enquiry must belong to the same branch"
        )
    check_branch_access(current_user, batch.branch_id)

    if payload.student_id is not None:
        student = db.get(Student, payload.student_id)
        if student is None or not student.is_active:
            raise HTTPException(status_code=400, detail="Active student does not exist")
        if student.branch_id != enquiry.branch_id:
            raise HTTPException(
                status_code=400, detail="Student and enquiry must belong to the same branch"
            )
    else:
        student = Student(
            student_code=_generate_student_code(db),
            full_name=enquiry.full_name,
            email=enquiry.email,
            phone=enquiry.phone,
            qualification=None,
            branch_id=enquiry.branch_id,
        )
        db.add(student)
        db.flush()

    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.batch_id == batch.id,
            Enrollment.status == "active",
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Student is already enrolled in this batch"
        )
    enrolled_count = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.batch_id == batch.id, Enrollment.status == "active"
        )
    ) or 0
    if enrolled_count >= batch.capacity:
        raise HTTPException(status_code=409, detail="Batch capacity has been reached")

    enrollment = Enrollment(
        enrollment_code=f"ENR-{datetime.now().year}-{uuid4().hex[:8].upper()}",
        student_id=student.id,
        batch_id=batch.id,
        admission_date=payload.admission_date,
        status="active",
    )
    db.add(enrollment)

    enquiry.status = "admitted"
    enquiry.student_id = student.id
    enquiry.converted_at = datetime.now()
    enquiry.follow_up_date = None
    record_audit(
        db,
        current_user.id,
        "enquiry_converted",
        "enquiry",
        enquiry.id,
        {"student_id": student.id, "batch_id": batch.id},
    )
    db.commit()
    db.refresh(enquiry)
    db.refresh(student)
    db.refresh(enrollment)
    return EnquiryConvertResponse(
        enquiry=EnquiryResponse.model_validate(enquiry),
        student=StudentResponse.model_validate(student),
        enrollment=EnrollmentResponse.model_validate(enrollment),
    )
