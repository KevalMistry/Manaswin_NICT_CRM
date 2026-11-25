from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import DatabaseSession, require_module, require_roles
from app.models.attendance import AttendanceSession
from app.models.branch import Branch
from app.models.responsibility import PerformanceReview, Responsibility
from app.models.role import Role
from app.models.user import User
from app.schemas.staff import (
    MANAGED_ROLES,
    ManagedRoleResponse,
    ManagedUserCreate,
    ManagedUserResponse,
    ManagedUserUpdate,
    PerformanceReviewCreate,
    PerformanceReviewResponse,
    PerformanceSummary,
    ResponsibilityCreate,
    ResponsibilityResponse,
    ResponsibilityUpdate,
)
from app.core.security import hash_password


router = APIRouter(prefix="/api/staff", tags=["Staff and Performance"])
ManageUsers = require_roles("Super Admin", "Branch Admin")
ManageAssignments = require_roles("Super Admin", "Branch Admin")
SUPER_ADMIN_MANAGED_ROLES = MANAGED_ROLES | {"Branch Admin"}
StaffDirectory = require_module("courses", "staff")
StaffAccess = require_module("staff")


def check_branch(current_user: User, branch_id: int) -> None:
    if current_user.role.name == "Branch Admin" and current_user.branch_id != branch_id:
        raise HTTPException(status_code=403, detail="You can manage only your assigned branch")


def managed_role(db: DatabaseSession, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if role is None or role.name not in MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Only Faculty, Staff, or Counsellor accounts can be managed here")
    return role


def manageable_role(db: DatabaseSession, role_id: int, current_user: User) -> Role:
    role = db.get(Role, role_id)
    if role is None or role.name not in allowed_managed_roles(current_user):
        raise HTTPException(status_code=400, detail="You cannot manage this account role")
    return role


def allowed_managed_roles(current_user: User) -> set[str]:
    return (
        SUPER_ADMIN_MANAGED_ROLES
        if current_user.role.name == "Super Admin"
        else MANAGED_ROLES
    )


@router.get(
    "/roles",
    response_model=list[ManagedRoleResponse],
    dependencies=[Depends(StaffAccess)],
)
def list_managed_roles(
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> list[ManagedRoleResponse]:
    """Return manageable roles with their database IDs.

    Role IDs are database-generated and can differ between installations, so
    clients must never hardcode them. Names are the stable contract.
    """
    allowed = allowed_managed_roles(current_user)
    roles = db.scalars(
        select(Role).where(
            Role.name.in_(allowed),
            Role.is_active.is_(True),
        )
    ).all()
    order = {name: index for index, name in enumerate(
        ("Branch Admin", "Faculty", "Staff", "Counsellor")
    )}
    ordered = sorted(roles, key=lambda role: order.get(role.name, len(order)))
    return [ManagedRoleResponse(id=role.id, name=role.name) for role in ordered]


def validate_managed_user(db: DatabaseSession, user_id: int, branch_id: int, current_user: User) -> User:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user_id))
    if user is None or user.role.name not in MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Assigned user must be Faculty, Staff, or Counsellor")
    check_branch(current_user, branch_id)
    if user.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="User and responsibility must belong to the same branch")
    return user


@router.get("/faculty", response_model=list[ManagedUserResponse], dependencies=[Depends(StaffDirectory)])
def list_faculty(
    db: DatabaseSession,
    current_user: User = Depends(require_roles("Super Admin", "Branch Admin", "Faculty", "Staff")),
) -> list[User]:
    query = select(User).join(Role).where(Role.name == "Faculty", User.is_active.is_(True))
    if current_user.role.name in {"Branch Admin", "Faculty", "Staff"}:
        query = query.where(User.branch_id == current_user.branch_id)
    return list(db.scalars(query.order_by(User.full_name)).all())


@router.get("/users", response_model=list[ManagedUserResponse], dependencies=[Depends(StaffAccess)])
def list_managed_users(
    db: DatabaseSession,
    current_user: User = Depends(ManageUsers),
    include_inactive: bool = Query(default=False),
) -> list[User]:
    roles = SUPER_ADMIN_MANAGED_ROLES if current_user.role.name == "Super Admin" else MANAGED_ROLES
    query = select(User).join(Role).where(Role.name.in_(roles))
    if current_user.role.name == "Branch Admin":
        query = query.where(User.branch_id == current_user.branch_id)
    if not include_inactive:
        query = query.where(User.is_active.is_(True))
    return list(db.scalars(query.order_by(User.full_name)).all())


@router.post("/users", response_model=ManagedUserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(StaffAccess)])
def create_managed_user(
    payload: ManagedUserCreate,
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> User:
    role = manageable_role(db, payload.role_id, current_user)
    check_branch(current_user, payload.branch_id)
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    branch = db.get(Branch, payload.branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=400, detail="Active branch does not exist")
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        phone=payload.phone,
        role_id=role.id,
        branch_id=payload.branch_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=ManagedUserResponse, dependencies=[Depends(StaffAccess)])
def update_managed_user(
    user_id: int,
    payload: ManagedUserUpdate,
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> User:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user_id))
    allowed_roles = SUPER_ADMIN_MANAGED_ROLES if current_user.role.name == "Super Admin" else MANAGED_ROLES
    if user is None or user.role.name not in allowed_roles:
        raise HTTPException(status_code=404, detail="Managed user not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Use Profile & settings to update your own account")
    check_branch(current_user, user.branch_id or 0)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and db.scalar(
        select(User).where(User.email == changes["email"], User.id != user_id)
    ):
        raise HTTPException(status_code=409, detail="Email is already registered")
    if "role_id" in changes:
        changes["role_id"] = manageable_role(db, changes["role_id"], current_user).id
    if "password" in changes:
        changes["hashed_password"] = hash_password(changes.pop("password"))
    if "branch_id" in changes and changes["branch_id"] is not None:
        check_branch(current_user, changes["branch_id"])
        branch = db.get(Branch, changes["branch_id"])
        if branch is None or not branch.is_active:
            raise HTTPException(status_code=400, detail="Active branch does not exist")
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(StaffAccess)])
def delete_managed_user(
    user_id: int,
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> None:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user_id))
    allowed_roles = SUPER_ADMIN_MANAGED_ROLES if current_user.role.name == "Super Admin" else MANAGED_ROLES
    if user is None or user.role.name not in allowed_roles:
        raise HTTPException(status_code=404, detail="Managed user not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.role.name == "Branch Admin" and current_user.role.name != "Super Admin":
        raise HTTPException(status_code=403, detail="Only Super Admin can delete a Branch Admin")
    check_branch(current_user, user.branch_id or 0)

    db.query(Responsibility).filter(
        (Responsibility.assigned_to_id == user_id)
        | (Responsibility.created_by_id == user_id)
    ).delete(synchronize_session=False)
    db.query(PerformanceReview).filter(
        (PerformanceReview.user_id == user_id)
        | (PerformanceReview.reviewed_by_id == user_id)
    ).delete(synchronize_session=False)
    db.query(AttendanceSession).filter(
        AttendanceSession.created_by_id == user_id
    ).update({"created_by_id": current_user.id}, synchronize_session=False)
    user.profile_photo_url = None
    db.delete(user)
    db.commit()


@router.get("/responsibilities", response_model=list[ResponsibilityResponse], dependencies=[Depends(StaffAccess)])
def list_responsibilities(
    db: DatabaseSession,
    current_user: User = Depends(ManageUsers),
    assigned_to_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[Responsibility]:
    query = select(Responsibility)
    if current_user.role.name in {"Branch Admin", "Staff"}:
        query = query.where(Responsibility.branch_id == current_user.branch_id)
    if assigned_to_id is not None:
        query = query.where(Responsibility.assigned_to_id == assigned_to_id)
    if status_filter is not None:
        query = query.where(Responsibility.status == status_filter)
    return list(db.scalars(query.order_by(Responsibility.created_at.desc())).all())


@router.post("/responsibilities", response_model=ResponsibilityResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(StaffAccess)])
def create_responsibility(
    payload: ResponsibilityCreate,
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> Responsibility:
    validate_managed_user(db, payload.assigned_to_id, payload.branch_id, current_user)
    item = Responsibility(created_by_id=current_user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/responsibilities/{responsibility_id}", response_model=ResponsibilityResponse, dependencies=[Depends(StaffAccess)])
def update_responsibility(
    responsibility_id: int,
    payload: ResponsibilityUpdate,
    db: DatabaseSession,
    current_user: User = Depends(ManageUsers),
) -> Responsibility:
    item = db.get(Responsibility, responsibility_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Responsibility not found")
    if current_user.role.name == "Staff" and item.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can update only your responsibilities")
    check_branch(current_user, item.branch_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/performance", response_model=PerformanceReviewResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(StaffAccess)])
def create_performance_review(
    payload: PerformanceReviewCreate,
    db: DatabaseSession,
    current_user: User = Depends(ManageAssignments),
) -> PerformanceReview:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == payload.user_id))
    if user is None or user.role.name not in MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Performance can only be recorded for Faculty, Staff, or Counsellor")
    check_branch(current_user, user.branch_id or 0)
    review = PerformanceReview(reviewed_by_id=current_user.id, **payload.model_dump())
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/performance/{user_id}", response_model=PerformanceSummary, dependencies=[Depends(StaffAccess)])
def get_performance(
    user_id: int,
    db: DatabaseSession,
    current_user: User = Depends(ManageUsers),
) -> PerformanceSummary:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user_id))
    if user is None or user.role.name not in MANAGED_ROLES:
        raise HTTPException(status_code=404, detail="Managed user not found")
    check_branch(current_user, user.branch_id or 0)
    assigned = db.scalar(select(func.count(Responsibility.id)).where(Responsibility.assigned_to_id == user_id)) or 0
    completed = db.scalar(select(func.count(Responsibility.id)).where(Responsibility.assigned_to_id == user_id, Responsibility.status == "completed")) or 0
    overdue = db.scalar(select(func.count(Responsibility.id)).where(Responsibility.assigned_to_id == user_id, Responsibility.due_date < date.today(), Responsibility.status.not_in(("completed", "cancelled")))) or 0
    follow_ups, admissions = db.execute(select(func.coalesce(func.sum(PerformanceReview.follow_ups_completed), 0), func.coalesce(func.sum(PerformanceReview.admissions_handled), 0)).where(PerformanceReview.user_id == user_id)).one()
    latest = db.scalar(select(PerformanceReview.rating).where(PerformanceReview.user_id == user_id).order_by(PerformanceReview.review_month.desc()).limit(1))
    return PerformanceSummary(user_id=user_id, assigned_responsibilities=assigned, completed_responsibilities=completed, overdue_responsibilities=overdue, follow_ups_completed=follow_ups, admissions_handled=admissions, latest_rating=latest)
