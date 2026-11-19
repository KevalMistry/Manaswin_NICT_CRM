from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    DatabaseSession,
    check_branch_access,
    require_module,
    require_roles,
)
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.user import User
from app.schemas.batch import BatchCreate, BatchResponse, BatchUpdate


router = APIRouter(prefix="/api/batches", tags=["Batches"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff")
BatchReader = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")
BatchesRead = require_module("courses", "enrollments", "attendance", "examinations", "certificates")
BatchesWrite = require_module("courses")


def validate_batch_references(
    payload: BatchCreate | BatchUpdate,
    db: DatabaseSession,
    current_user: User,
    existing: Batch | None = None,
) -> None:
    branch_id = payload.branch_id if payload.branch_id is not None else existing.branch_id
    course_id = payload.course_id if payload.course_id is not None else existing.course_id
    faculty_id = payload.faculty_id if payload.faculty_id is not None else (
        existing.faculty_id if existing else None
    )

    check_branch_access(current_user, branch_id)
    branch = db.get(Branch, branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=400, detail="Active branch does not exist")
    course = db.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=400, detail="Active course does not exist")
    if faculty_id is not None:
        faculty = db.get(User, faculty_id)
        if (
            faculty is None
            or not faculty.is_active
            or faculty.branch_id != branch_id
            or faculty.role.name != "Faculty"
        ):
            raise HTTPException(
                status_code=400,
                detail="Faculty must be an active Faculty user assigned to the batch branch",
            )


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(BatchesWrite)])
def create_batch(
    payload: BatchCreate,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Batch:
    if db.scalar(select(Batch).where(Batch.code == payload.code)) is not None:
        raise HTTPException(status_code=409, detail="Batch code already exists")
    validate_batch_references(payload, db, current_user)
    batch = Batch(**payload.model_dump())
    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Batch code already exists") from None
    db.refresh(batch)
    return batch


@router.get("", response_model=list[BatchResponse], dependencies=[Depends(BatchesRead)])
def list_batches(
    db: DatabaseSession,
    current_user: User = Depends(BatchReader),
    branch_id: int | None = Query(default=None),
    course_id: int | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Batch]:
    check_branch_access(current_user, branch_id)
    if current_user.role.name != "Super Admin":
        branch_id = current_user.branch_id
    if current_user.role.name == "Faculty":
        query = select(Batch).where(Batch.faculty_id == current_user.id).order_by(Batch.start_date.desc()).offset(offset).limit(limit)
    else:
        query = select(Batch).order_by(Batch.start_date.desc()).offset(offset).limit(limit)
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if course_id is not None:
        query = query.where(Batch.course_id == course_id)
    if not include_inactive:
        query = query.where(Batch.is_active.is_(True))
    return list(db.scalars(query).all())


@router.get("/{batch_id}", response_model=BatchResponse, dependencies=[Depends(BatchesRead)])
def get_batch(
    batch_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    check_branch_access(current_user, batch.branch_id)
    return batch


@router.patch("/{batch_id}", response_model=BatchResponse, dependencies=[Depends(BatchesWrite)])
def update_batch(
    batch_id: int,
    payload: BatchUpdate,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    check_branch_access(current_user, batch.branch_id)
    validate_batch_references(payload, db, current_user, batch)
    changes = payload.model_dump(exclude_unset=True)
    non_nullable = {"name", "code", "course_id", "branch_id", "start_date", "capacity", "is_active"}
    invalid = sorted(field for field in non_nullable if field in changes and changes[field] is None)
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"These fields cannot be null: {', '.join(invalid)}",
        )
    if "code" in changes and db.scalar(
        select(Batch).where(Batch.code == changes["code"], Batch.id != batch_id)
    ) is not None:
        raise HTTPException(status_code=409, detail="Batch code already exists")
    for field, value in changes.items():
        setattr(batch, field, value)
    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}", response_model=BatchResponse, dependencies=[Depends(BatchesWrite)])
def deactivate_batch(
    batch_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    check_branch_access(current_user, batch.branch_id)
    batch.is_active = False
    db.commit()
    db.refresh(batch)
    return batch
