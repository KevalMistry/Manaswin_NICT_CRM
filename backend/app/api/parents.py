from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.api.audit import record_audit
from app.api.dependencies import DatabaseSession, branch_scope, require_module, require_roles
from app.core.security import hash_password
from app.models.branch import Branch
from app.models.parent import ParentStudentLink
from app.models.role import Role
from app.models.student import Student
from app.models.user import User
from app.schemas.parent import (
    ParentAccountCreate,
    ParentAccountResponse,
    ParentAccountUpdate,
    ParentChildLinkResponse,
    ParentLinkCreate,
    ParentPasswordReset,
)


router = APIRouter(prefix="/api/parents", tags=["Parents"])
# Managing guardian logins is part of student administration, so it reuses the
# students module permission instead of adding another configurable module.
ParentsAccess = require_module("students")
ParentsAdmin = require_roles("Super Admin", "Branch Admin", "Staff")
PARENT_ROLE_NAME = "Parent"


def _check_branch_access(current_user: User, branch_id: int) -> None:
    if current_user.role.name == "Super Admin":
        return
    if current_user.branch_id is None or current_user.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this branch",
        )


def _parent_role(db: DatabaseSession) -> Role:
    role = db.scalar(select(Role).where(Role.name == PARENT_ROLE_NAME))
    if role is None:
        raise HTTPException(
            status_code=500, detail="Parent role is not configured"
        )
    return role


def _parent_user(db: DatabaseSession, parent_user_id: int) -> User:
    user = db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == parent_user_id)
    )
    if user is None or user.role is None or user.role.name != PARENT_ROLE_NAME:
        raise HTTPException(status_code=404, detail="Parent account not found")
    return user


def _child_rows(
    db: DatabaseSession, parent_ids: list[int]
) -> dict[int, list[ParentChildLinkResponse]]:
    if not parent_ids:
        return {}
    links = db.scalars(
        select(ParentStudentLink)
        .options(joinedload(ParentStudentLink.student))
        .where(ParentStudentLink.parent_user_id.in_(parent_ids))
        .order_by(ParentStudentLink.id)
    ).all()
    grouped: dict[int, list[ParentChildLinkResponse]] = {}
    for link in links:
        grouped.setdefault(link.parent_user_id, []).append(
            ParentChildLinkResponse(
                link_id=link.id,
                student_id=link.student_id,
                student_code=link.student.student_code,
                student_name=link.student.full_name,
                relationship=link.relationship,
                is_primary=link.is_primary,
            )
        )
    return grouped


def _branch_names(db: DatabaseSession, branch_ids: set[int]) -> dict[int, str]:
    ids = [branch_id for branch_id in branch_ids if branch_id is not None]
    if not ids:
        return {}
    rows = db.execute(
        select(Branch.id, Branch.name).where(Branch.id.in_(ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def _parent_response(
    user: User,
    children: list[ParentChildLinkResponse],
    branch_names: dict[int, str],
) -> ParentAccountResponse:
    return ParentAccountResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        branch_id=user.branch_id,
        branch_name=branch_names.get(user.branch_id) if user.branch_id else None,
        is_active=user.is_active,
        created_at=user.created_at,
        children=children,
    )


def _link_student(
    db: DatabaseSession,
    current_user: User,
    parent: User,
    student_id: int,
    relationship: str,
) -> ParentStudentLink:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)
    existing = db.scalar(
        select(ParentStudentLink).where(
            ParentStudentLink.parent_user_id == parent.id,
            ParentStudentLink.student_id == student.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This student is already linked to the parent account",
        )
    link = ParentStudentLink(
        parent_user_id=parent.id,
        student_id=student.id,
        relationship=relationship.strip() or "Guardian",
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "parent_student_linked",
        "parent",
        parent.id,
        {"student_id": student.id, "relationship": link.relationship},
    )
    return link


@router.get(
    "",
    response_model=list[ParentAccountResponse],
    dependencies=[Depends(ParentsAccess)],
)
def list_parent_accounts(
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> list[ParentAccountResponse]:
    query = (
        select(User)
        .options(joinedload(User.role))
        .join(Role, User.role_id == Role.id)
        .where(Role.name == PARENT_ROLE_NAME)
        .order_by(User.full_name)
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(User.branch_id == scope)
    parents = db.scalars(query).unique().all()
    children = _child_rows(db, [parent.id for parent in parents])
    branch_names = _branch_names(db, {parent.branch_id for parent in parents})
    return [
        _parent_response(
            parent,
            children.get(parent.id, []),
            branch_names,
        )
        for parent in parents
    ]


@router.post(
    "",
    response_model=ParentAccountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ParentsAccess)],
)
def create_parent_account(
    payload: ParentAccountCreate,
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> ParentAccountResponse:
    role = _parent_role(db)
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")

    branch_id = payload.branch_id or current_user.branch_id
    student_ids = list(dict.fromkeys(payload.student_ids))
    if not student_ids:
        raise HTTPException(
            status_code=400,
            detail="Link at least one student to the parent account",
        )
    students = []
    for student_id in student_ids:
        student = db.get(Student, student_id)
        if student is None:
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
        _check_branch_access(current_user, student.branch_id)
        students.append(student)
    if branch_id is None and students:
        branch_id = students[0].branch_id
    if branch_id is None:
        raise HTTPException(
            status_code=400, detail="A branch is required for the parent account"
        )
    _check_branch_access(current_user, branch_id)
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=404, detail="Branch not found")

    parent = User(
        full_name=payload.full_name,
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        phone=payload.phone,
        role_id=role.id,
        branch_id=branch_id,
    )
    db.add(parent)
    db.flush()
    for student_id in student_ids:
        _link_student(db, current_user, parent, student_id, payload.relationship)
    record_audit(
        db,
        current_user.id,
        "parent_account_created",
        "parent",
        parent.id,
        {"user_id": parent.id, "student_ids": student_ids},
    )
    db.commit()
    db.refresh(parent)
    children = _child_rows(db, [parent.id]).get(parent.id, [])
    branch_names = _branch_names(db, {parent.branch_id})
    return _parent_response(parent, children, branch_names)


@router.patch(
    "/{parent_user_id}",
    response_model=ParentAccountResponse,
    dependencies=[Depends(ParentsAccess)],
)
def update_parent_account(
    parent_user_id: int,
    payload: ParentAccountUpdate,
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> ParentAccountResponse:
    parent = _parent_user(db, parent_user_id)
    if parent.branch_id is not None:
        _check_branch_access(current_user, parent.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    for field in ("full_name", "email", "branch_id"):
        if field in changes and changes[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )
    if "email" in changes:
        email = str(changes["email"])
        duplicate = db.scalar(
            select(User.id).where(User.email == email, User.id != parent.id)
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Email is already registered")
        changes["email"] = email
    if "branch_id" in changes and changes["branch_id"] != parent.branch_id:
        branch = db.get(Branch, changes["branch_id"])
        if branch is None:
            raise HTTPException(status_code=404, detail="Branch not found")
        _check_branch_access(current_user, branch.id)
    for field, value in changes.items():
        setattr(parent, field, value)
    record_audit(
        db,
        current_user.id,
        "parent_account_updated",
        "parent",
        parent.id,
        changes,
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request may register the same email between the check
        # above and this commit; report it the same way as the pre-check.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from None
    db.refresh(parent)
    children = _child_rows(db, [parent.id]).get(parent.id, [])
    branch_names = _branch_names(db, {parent.branch_id})
    return _parent_response(parent, children, branch_names)


@router.post(
    "/{parent_user_id}/password",
    response_model=ParentAccountResponse,
    dependencies=[Depends(ParentsAccess)],
)
def reset_parent_password(
    parent_user_id: int,
    payload: ParentPasswordReset,
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> ParentAccountResponse:
    parent = _parent_user(db, parent_user_id)
    if parent.branch_id is not None:
        _check_branch_access(current_user, parent.branch_id)
    parent.hashed_password = hash_password(payload.password)
    record_audit(
        db,
        current_user.id,
        "parent_password_reset",
        "parent",
        parent.id,
        {},
    )
    db.commit()
    children = _child_rows(db, [parent.id]).get(parent.id, [])
    branch_names = _branch_names(db, {parent.branch_id})
    return _parent_response(parent, children, branch_names)


@router.post(
    "/{parent_user_id}/children",
    response_model=ParentAccountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ParentsAccess)],
)
def link_parent_student(
    parent_user_id: int,
    payload: ParentLinkCreate,
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> ParentAccountResponse:
    parent = _parent_user(db, parent_user_id)
    if parent.branch_id is not None:
        _check_branch_access(current_user, parent.branch_id)
    _link_student(db, current_user, parent, payload.student_id, payload.relationship)
    db.commit()
    children = _child_rows(db, [parent.id]).get(parent.id, [])
    branch_names = _branch_names(db, {parent.branch_id})
    return _parent_response(parent, children, branch_names)


@router.delete(
    "/{parent_user_id}/children/{student_id}",
    response_model=ParentAccountResponse,
    dependencies=[Depends(ParentsAccess)],
)
def unlink_parent_student(
    parent_user_id: int,
    student_id: int,
    db: DatabaseSession,
    current_user: User = Depends(ParentsAdmin),
) -> ParentAccountResponse:
    parent = _parent_user(db, parent_user_id)
    if parent.branch_id is not None:
        _check_branch_access(current_user, parent.branch_id)
    link = db.scalar(
        select(ParentStudentLink).where(
            ParentStudentLink.parent_user_id == parent.id,
            ParentStudentLink.student_id == student_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Student link not found")
    db.delete(link)
    record_audit(
        db,
        current_user.id,
        "parent_student_unlinked",
        "parent",
        parent.id,
        {"student_id": student_id},
    )
    db.commit()
    children = _child_rows(db, [parent.id]).get(parent.id, [])
    branch_names = _branch_names(db, {parent.branch_id})
    return _parent_response(parent, children, branch_names)
