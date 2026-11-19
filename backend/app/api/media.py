"""Authenticated access to files stored under ``backend/uploads``.

Uploaded student photos, KYC documents and LMS submissions used to be exposed
by a public ``/uploads`` static mount. That let anyone who guessed a path read
student documents. Files are now served through this route, which resolves the
linked record and checks that the signed-in principal may see it.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import DatabaseSession, get_current_user, has_module_access
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.enrollment import Enrollment
from app.models.lms import AssignmentSubmission
from app.models.parent import ParentStudentLink
from app.models.student import Student
from app.models.student_document import StudentDocument
from app.models.user import User


router = APIRouter(prefix="/api/media", tags=["Media"])

UPLOADS_DIR = (Path(__file__).resolve().parents[2] / "uploads").resolve()
STAFF_ROLES = {"Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor"}


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
    )


def _is_own_student(user: User, student: Student) -> bool:
    return user.role.name == "Student" and student.user_id == user.id


def _is_linked_parent(db: Session, user: User, student_id: int) -> bool:
    if user.role.name != "Parent":
        return False
    return (
        db.scalar(
            select(ParentStudentLink.id).where(
                ParentStudentLink.parent_user_id == user.id,
                ParentStudentLink.student_id == student_id,
            )
        )
        is not None
    )


def _staff_can_view_student(
    db: Session, user: User, student: Student, module_key: str = "students"
) -> bool:
    if user.role.name == "Super Admin":
        return True
    if user.role.name not in STAFF_ROLES:
        return False
    if not has_module_access(user, db, module_key):
        return False
    if user.role.name == "Faculty":
        # Faculty are confined to batches they actually teach.
        return (
            db.scalar(
                select(Enrollment.id)
                .join(Batch, Enrollment.batch_id == Batch.id)
                .where(
                    Enrollment.student_id == student.id,
                    Batch.faculty_id == user.id,
                )
            )
            is not None
        )
    return user.branch_id is not None and user.branch_id == student.branch_id


def _authorize_student_path(
    db: Session, user: User, parts: list[str], file_url: str
) -> None:
    try:
        student_id = int(parts[1])
    except (IndexError, ValueError):
        raise _not_found() from None

    student = db.get(Student, student_id)
    if student is None:
        raise _not_found()

    if len(parts) >= 3 and parts[2] == "documents":
        document = db.scalar(
            select(StudentDocument).where(
                StudentDocument.student_id == student.id,
                StudentDocument.file_url == file_url,
            )
        )
        if document is None:
            raise _not_found()
    elif student.photo_url != file_url:
        # Only the photo currently recorded on the student is served, not any
        # stale or unrelated file that happens to live in the same folder.
        raise _not_found()

    allowed = (
        _is_own_student(user, student)
        or _is_linked_parent(db, user, student.id)
        or _staff_can_view_student(db, user, student)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this file",
        )


def _authorize_branch_payment_path(
    db: Session, user: User, parts: list[str], file_url: str
) -> None:
    try:
        branch_id = int(parts[1])
    except (IndexError, ValueError):
        raise _not_found() from None
    if len(parts) != 4 or parts[2] != "payment":
        raise _not_found()
    branch = db.get(Branch, branch_id)
    if branch is None or branch.upi_qr_code_url != file_url:
        raise _not_found()
    if user.role.name == "Super Admin":
        return
    if user.branch_id != branch_id:
        raise _not_found()


def _authorize_lms_path(db: Session, user: User, file_url: str) -> None:
    submission = db.scalar(
        select(AssignmentSubmission).where(
            AssignmentSubmission.file_url == file_url
        )
    )
    if submission is None:
        raise _not_found()

    enrollment = db.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.batch))
        .where(Enrollment.id == submission.enrollment_id)
    )
    if enrollment is None or enrollment.batch is None:
        raise _not_found()

    if user.role.name == "Super Admin":
        return
    if user.role.name == "Student":
        student = db.get(Student, enrollment.student_id)
        if student is not None and student.user_id == user.id:
            return
    elif user.role.name in STAFF_ROLES and has_module_access(user, db, "lms"):
        if user.role.name == "Faculty":
            if enrollment.batch.faculty_id == user.id:
                return
        elif user.branch_id is not None and user.branch_id == enrollment.batch.branch_id:
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this file",
    )


def _resolve_file(file_path: str) -> Path:
    candidate = (UPLOADS_DIR / file_path).resolve()
    if not candidate.is_relative_to(UPLOADS_DIR) or not candidate.is_file():
        raise _not_found()
    return candidate


@router.get("/{file_path:path}")
def get_media_file(
    file_path: str,
    db: DatabaseSession,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve one upload after checking the caller may access the linked record."""
    normalised = file_path.strip("/")
    parts = normalised.split("/")
    file_url = f"/uploads/{normalised}"

    if not parts or parts[0] not in {"profiles", "students", "branches", "lms"}:
        raise _not_found()

    if parts[0] == "profiles":
        # Profile photos are visible to every signed-in user, but only files
        # recorded on an account are served.
        if len(parts) != 2 or db.scalar(
            select(User.id).where(User.profile_photo_url == file_url)
        ) is None:
            raise _not_found()
    elif parts[0] == "students":
        _authorize_student_path(db, current_user, parts, file_url)
    elif parts[0] == "branches":
        _authorize_branch_payment_path(db, current_user, parts, file_url)
    else:
        _authorize_lms_path(db, current_user, file_url)

    path = _resolve_file(normalised)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
