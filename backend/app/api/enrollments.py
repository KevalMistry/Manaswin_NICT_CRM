from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    DatabaseSession,
    check_branch_access,
    require_module,
    require_roles,
)
from app.models.batch import Batch
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.user import User
from app.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentResponse,
    EnrollmentStatusUpdate,
)


router = APIRouter(prefix="/api/enrollments", tags=["Enrollments"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff", "Counsellor")
EnrollmentReader = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")
EnrollmentsRead = require_module("enrollments", "attendance", "examinations", "certificates")
EnrollmentsWrite = require_module("enrollments")


def branch_allowed(current_user: User, branch_id: int) -> None:
    check_branch_access(current_user, branch_id)


# Faculty cannot open the Enrollments module (the frontend route and nav item
# require the "enrollments" module, which Faculty does not have). Faculty reads
# this endpoint only through attendance/examinations/certificates, and the list
# query below restricts Faculty to batches they actually teach.


@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(EnrollmentsWrite)])
def create_enrollment(
    payload: EnrollmentCreate,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Enrollment:
    student = db.get(Student, payload.student_id)
    batch = db.get(Batch, payload.batch_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=400, detail="Active student does not exist")
    if batch is None or not batch.is_active:
        raise HTTPException(status_code=400, detail="Active batch does not exist")
    if student.branch_id != batch.branch_id:
        raise HTTPException(status_code=400, detail="Student and batch must belong to the same branch")
    branch_allowed(current_user, batch.branch_id)
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == payload.student_id,
            Enrollment.batch_id == payload.batch_id,
            Enrollment.status == "active",
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Student is already enrolled in this batch")
    enrolled_count = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.batch_id == batch.id, Enrollment.status == "active"
        )
    ) or 0
    if enrolled_count >= batch.capacity:
        raise HTTPException(status_code=409, detail="Batch capacity has been reached")
    enrollment = Enrollment(
        enrollment_code=f"ENR-{datetime.now().year}-{uuid4().hex[:8].upper()}",
        **payload.model_dump(),
    )
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Enrollment already exists") from None
    db.refresh(enrollment)
    return enrollment


@router.get("", response_model=list[EnrollmentResponse], dependencies=[Depends(EnrollmentsRead)])
def list_enrollments(
    db: DatabaseSession,
    current_user: User = Depends(EnrollmentReader),
    branch_id: int | None = Query(default=None),
    student_id: int | None = Query(default=None),
    batch_id: int | None = Query(default=None),
    include_cancelled: bool = False,
) -> list[Enrollment]:
    check_branch_access(current_user, branch_id)
    if current_user.role.name != "Super Admin":
        branch_id = current_user.branch_id
    query = select(Enrollment).join(Batch, Enrollment.batch_id == Batch.id)
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if student_id is not None:
        query = query.where(Enrollment.student_id == student_id)
    if batch_id is not None:
        query = query.where(Enrollment.batch_id == batch_id)
    if current_user.role.name == "Faculty":
        query = query.where(Batch.faculty_id == current_user.id)
    if not include_cancelled:
        query = query.where(Enrollment.status != "cancelled")
    return list(db.scalars(query.order_by(Enrollment.created_at.desc())).all())


@router.patch("/{enrollment_id}", response_model=EnrollmentResponse, dependencies=[Depends(EnrollmentsWrite)])
def update_enrollment_status(
    enrollment_id: int,
    payload: EnrollmentStatusUpdate,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Enrollment:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    batch = db.get(Batch, enrollment.batch_id)
    branch_allowed(current_user, batch.branch_id)

    if payload.status == "active" and enrollment.status != "active":
        student = db.get(Student, enrollment.student_id)
        if student is None or not student.is_active:
            raise HTTPException(status_code=400, detail="Active student does not exist")
        if batch is None or not batch.is_active:
            raise HTTPException(status_code=400, detail="Active batch does not exist")
        duplicate = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == enrollment.student_id,
                Enrollment.batch_id == enrollment.batch_id,
                Enrollment.status == "active",
                Enrollment.id != enrollment.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=409, detail="Student is already enrolled in this batch"
            )
        enrolled_count = db.scalar(
            select(func.count(Enrollment.id)).where(
                Enrollment.batch_id == batch.id,
                Enrollment.status == "active",
                Enrollment.id != enrollment.id,
            )
        ) or 0
        if enrolled_count >= batch.capacity:
            raise HTTPException(status_code=409, detail="Batch capacity has been reached")

    enrollment.status = payload.status
    db.commit()
    db.refresh(enrollment)
    return enrollment
