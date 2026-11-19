from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    require_module,
    require_roles,
)
from app.api.audit import record_audit
from app.core.uploads import content_matches_extension
from app.core.security import hash_password
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.student_document import StudentDocument
from app.models.user import User
from app.models.role import Role
from app.schemas.student import (
    StudentAccountCreate,
    StudentAccountResponse,
    StudentCreate,
    StudentDocumentResponse,
    StudentResponse,
    StudentUpdate,
)


router = APIRouter(prefix="/api/students", tags=["Students"])
ManageStudentUser = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff")
# Counsellors may create and edit enquiry/student records, but they cannot
# deactivate students or create student login accounts.
StudentEditor = require_roles("Super Admin", "Branch Admin", "Staff", "Counsellor")
StudentsRead = require_module("students", "attendance", "enrollments", "examinations", "certificates")
StudentsWrite = require_module("students")

STUDENT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "students"
PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_PHOTO_SIZE = 3 * 1024 * 1024
DOCUMENT_TYPES = {
    "aadhaar": "Aadhaar Card",
    "pan": "PAN Card",
    "photo": "Photograph",
    "marksheet": "Marksheet",
    "certificate": "Certificate",
    "id_proof": "ID Proof",
    "other": "Other",
}
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".zip"}
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024


@router.post(
    "/{student_id}/account",
    response_model=StudentAccountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(StudentsWrite)],
)
def create_student_account(
    student_id: int,
    payload: StudentAccountCreate,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> StudentAccountResponse:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)
    if student.user_id is not None:
        raise HTTPException(status_code=409, detail="Student already has a login account")
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    role = db.scalar(select(Role).where(Role.name == "Student"))
    if role is None:
        raise HTTPException(status_code=500, detail="Student role is not configured")
    user = User(
        full_name=student.full_name,
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        phone=student.phone,
        role_id=role.id,
        branch_id=student.branch_id,
    )
    db.add(user)
    db.flush()
    student.user_id = user.id
    record_audit(
        db,
        current_user.id,
        "student_account_created",
        "student",
        student.id,
        {"user_id": user.id},
    )
    db.commit()
    return StudentAccountResponse(student_id=student.id, user_id=user.id, email=payload.email)


def _check_branch_access(current_user: User, branch_id: int) -> None:
    if current_user.role.name == "Super Admin":
        return
    if current_user.branch_id is None or current_user.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can access students only in your assigned branch",
        )


def _generate_student_code(db: DatabaseSession) -> str:
    year = datetime.now().year
    for _ in range(5):
        candidate = f"STU-{year}-{uuid4().hex[:8].upper()}"
        if db.scalar(select(Student.id).where(Student.student_code == candidate)) is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not generate a unique student ID",
    )


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(StudentsWrite)],
)
def create_student(
    payload: StudentCreate,
    db: DatabaseSession,
    current_user: User = Depends(StudentEditor),
) -> Student:
    branch = db.get(Branch, payload.branch_id)
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=400, detail="Active branch does not exist")
    _check_branch_access(current_user, payload.branch_id)

    student = Student(
        student_code=_generate_student_code(db),
        **payload.model_dump(),
    )
    db.add(student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create student") from None
    db.refresh(student)
    return student


@router.get("", response_model=list[StudentResponse], dependencies=[Depends(StudentsRead)])
def list_students(
    db: DatabaseSession,
    current_user: User = Depends(ManageStudentUser),
    branch_id: int | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Student]:
    scope = branch_scope(current_user)
    if branch_id is not None and scope is not None and branch_id != scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can access students only in your assigned branch",
        )
    requested_branch = branch_id if branch_id is not None else scope

    query = select(Student).order_by(Student.full_name).offset(offset).limit(limit)
    if requested_branch is not None:
        query = query.where(Student.branch_id == requested_branch)
    if not include_inactive:
        query = query.where(Student.is_active.is_(True))
    if search:
        query = query.where(Student.full_name.ilike(f"%{search}%"))
    return list(db.scalars(query).all())


@router.get("/{student_id}", response_model=StudentResponse, dependencies=[Depends(StudentsRead)])
def get_student(
    student_id: int,
    db: DatabaseSession,
    current_user: User = Depends(ManageStudentUser),
) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)
    return student


@router.patch("/{student_id}", response_model=StudentResponse, dependencies=[Depends(StudentsWrite)])
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StudentEditor),
) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)

    changes = payload.model_dump(exclude_unset=True)
    if current_user.role.name == "Counsellor" and "is_active" in changes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Counsellors cannot activate or deactivate students",
        )
    non_nullable = {"full_name", "branch_id", "is_active"}
    invalid = sorted(field for field in non_nullable if field in changes and changes[field] is None)
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"These fields cannot be null: {', '.join(invalid)}",
        )
    branch_changed = (
        "branch_id" in changes and changes["branch_id"] != student.branch_id
    )
    if branch_changed:
        target_branch = db.get(Branch, changes["branch_id"])
        if target_branch is None or not target_branch.is_active:
            raise HTTPException(status_code=400, detail="Active branch does not exist")
        _check_branch_access(current_user, changes["branch_id"])
        # Enrollments point at a batch, and a batch belongs to one branch. Block
        # the move until the student's active classes are transferred or closed.
        active_elsewhere = db.scalar(
            select(Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(
                Enrollment.student_id == student.id,
                Enrollment.status == "active",
                Batch.branch_id != changes["branch_id"],
            )
        )
        if active_elsewhere is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Transfer or cancel this student's active enrollments before "
                    "changing their branch"
                ),
            )

    for field, value in changes.items():
        setattr(student, field, value)
    linked_user = (
        db.get(User, student.user_id) if student.user_id is not None else None
    )
    if linked_user is not None:
        if "is_active" in changes:
            linked_user.is_active = student.is_active
        if branch_changed:
            # Keep the login account aligned with the student's new branch so
            # branch-scoped endpoints do not keep using the old one.
            linked_user.branch_id = student.branch_id
    db.commit()
    db.refresh(student)
    return student


@router.delete("/{student_id}", response_model=StudentResponse, dependencies=[Depends(StudentsWrite)])
def deactivate_student(
    student_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AdminUser),
) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)
    student.is_active = False
    if student.user_id is not None:
        linked_user = db.get(User, student.user_id)
        if linked_user is not None:
            linked_user.is_active = False
    db.commit()
    db.refresh(student)
    return student


def _get_scoped_student(db: DatabaseSession, student_id: int, current_user: User) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    _check_branch_access(current_user, student.branch_id)
    return student


@router.post(
    "/{student_id}/photo",
    response_model=StudentResponse,
    dependencies=[Depends(StudentsWrite)],
)
async def upload_student_photo(
    student_id: int,
    db: DatabaseSession,
    file: UploadFile = File(...),
    current_user: User = Depends(StudentEditor),
) -> Student:
    student = _get_scoped_student(db, student_id, current_user)

    content_type = (file.content_type or "").lower()
    extension = PHOTO_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(
            status_code=400,
            detail="Upload a JPG, PNG or WebP image for the student photo",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded photo is empty")
    if len(data) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=400, detail="The student photo must be 3 MB or smaller")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image") from None

    directory = STUDENT_UPLOAD_DIR / str(student.id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"photo-{uuid4().hex}{extension}"
    (directory / filename).write_bytes(data)

    previous_url = student.photo_url
    student.photo_url = f"/uploads/students/{student.id}/{filename}"
    record_audit(
        db,
        current_user.id,
        "student_photo_uploaded",
        "student",
        student.id,
        {"file": filename},
    )
    db.commit()
    db.refresh(student)

    if previous_url and previous_url.startswith("/uploads/students/"):
        previous_path = STUDENT_UPLOAD_DIR.parent.parent / previous_url.lstrip("/")
        previous_path.unlink(missing_ok=True)
    return student


@router.get(
    "/{student_id}/documents",
    response_model=list[StudentDocumentResponse],
    dependencies=[Depends(StudentsRead)],
)
def list_student_documents(
    student_id: int,
    db: DatabaseSession,
    current_user: User = Depends(ManageStudentUser),
) -> list[StudentDocument]:
    _get_scoped_student(db, student_id, current_user)
    return list(
        db.scalars(
            select(StudentDocument)
            .where(StudentDocument.student_id == student_id)
            .order_by(StudentDocument.uploaded_at.desc(), StudentDocument.id.desc())
        ).all()
    )


@router.post(
    "/{student_id}/documents",
    response_model=StudentDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(StudentsWrite)],
)
async def upload_student_document(
    student_id: int,
    db: DatabaseSession,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    title: str = Form(default=""),
    current_user: User = Depends(StudentEditor),
) -> StudentDocument:
    student = _get_scoped_student(db, student_id, current_user)

    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Choose a valid document type")

    original_name = Path(file.filename or "document").name
    extension = Path(original_name).suffix.lower()
    if extension not in DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Document must be a PDF, image, Word, Excel or ZIP file",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded document is empty")
    if len(data) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=400, detail="The document must be 10 MB or smaller")
    if not content_matches_extension(extension, data):
        raise HTTPException(
            status_code=400,
            detail="The file content does not match its type. Upload a genuine file.",
        )

    directory = STUDENT_UPLOAD_DIR / str(student.id) / "documents"
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{document_type}-{uuid4().hex}{extension}"
    (directory / stored_name).write_bytes(data)

    document = StudentDocument(
        student_id=student.id,
        document_type=document_type,
        title=title.strip() or DOCUMENT_TYPES[document_type],
        file_name=original_name,
        file_url=f"/uploads/students/{student.id}/documents/{stored_name}",
        content_type=file.content_type,
        file_size=len(data),
        uploaded_by_id=current_user.id,
    )
    db.add(document)
    record_audit(
        db,
        current_user.id,
        "student_document_uploaded",
        "student",
        student.id,
        {"document_type": document_type, "file": original_name},
    )
    db.commit()
    db.refresh(document)
    return document


@router.delete(
    "/{student_id}/documents/{document_id}",
    response_model=StudentDocumentResponse,
    dependencies=[Depends(StudentsWrite)],
)
def delete_student_document(
    student_id: int,
    document_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentEditor),
) -> StudentDocumentResponse:
    _get_scoped_student(db, student_id, current_user)
    document = db.get(StudentDocument, document_id)
    if document is None or document.student_id != student_id:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = StudentDocumentResponse.model_validate(document)
    file_url = document.file_url
    db.delete(document)
    record_audit(
        db,
        current_user.id,
        "student_document_deleted",
        "student",
        student_id,
        {"document_id": document_id},
    )
    db.commit()

    if file_url.startswith("/uploads/students/"):
        file_path = STUDENT_UPLOAD_DIR.parent.parent / file_url.lstrip("/")
        file_path.unlink(missing_ok=True)
    return snapshot
