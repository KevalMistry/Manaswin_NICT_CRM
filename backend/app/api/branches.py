from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    require_module,
    require_roles,
)
from app.models.branch import Branch
from app.models.user import User
from app.schemas.branch import BranchCreate, BranchResponse, BranchUpdate
from app.services.certificate_templates import sanitize_template


router = APIRouter(prefix="/api/branches", tags=["Branches"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff")
DesignUser = require_roles("Super Admin", "Branch Admin", "Staff")
SuperAdmin = require_roles("Super Admin")
DirectoryReader = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")
BranchRead = require_module(
    "branches", "students", "courses", "staff", "enrollments",
    "fees", "attendance", "examinations", "certificates", "permissions",
)
BranchWrite = require_module("branches")
PAYMENT_QR_DIR = Path(__file__).resolve().parents[2] / "uploads" / "branches"
MAX_PAYMENT_QR_SIZE = 3 * 1024 * 1024
PAYMENT_QR_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@router.post(
    "",
    response_model=BranchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(SuperAdmin), Depends(BranchWrite)],
)
def create_branch(payload: BranchCreate, db: DatabaseSession) -> Branch:
    if db.scalar(select(Branch).where(Branch.code == payload.code)) is not None:
        raise HTTPException(status_code=409, detail="Branch code already exists")

    values = payload.model_dump()
    for field, document_type in (
        ("certificate_template", "certificate"),
        ("marksheet_template", "marksheet"),
    ):
        try:
            if values[field]:
                values[field] = sanitize_template(values[field], document_type=document_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    branch = Branch(**values)
    db.add(branch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A branch with the submitted unique value already exists",
        ) from None
    db.refresh(branch)
    return branch


@router.get("", response_model=list[BranchResponse], dependencies=[Depends(BranchRead)])
def list_branches(
    response: Response,
    db: DatabaseSession,
    current_user: User = Depends(DirectoryReader),
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Branch]:
    response.headers["Cache-Control"] = "private, no-store"
    query = select(Branch).order_by(Branch.name).offset(offset).limit(limit)
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Branch.id == scope)
    if not include_inactive:
        query = query.where(Branch.is_active.is_(True))
    return list(db.scalars(query).all())


@router.get("/{branch_id}", response_model=BranchResponse, dependencies=[Depends(BranchRead)])
def get_branch(
    branch_id: int,
    db: DatabaseSession,
    current_user: object = Depends(AdminUser),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    if current_user.role.name == "Branch Admin" and current_user.branch_id != branch_id:
        raise HTTPException(status_code=403, detail="You can access only your assigned branch")
    return branch


@router.patch("/{branch_id}", response_model=BranchResponse)
def update_branch(
    branch_id: int,
    payload: BranchUpdate,
    db: DatabaseSession,
    current_user: User = Depends(DesignUser),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")

    changes = payload.model_dump(exclude_unset=True)
    design_fields = {
        "certificate_title",
        "marksheet_title",
        "certificate_primary_color",
        "certificate_accent_color",
        "certificate_template",
        "marksheet_template",
    }
    if current_user.role.name != "Super Admin":
        if current_user.branch_id != branch_id:
            raise HTTPException(status_code=403, detail="You can update only your assigned branch")
        changes = {field: value for field, value in changes.items() if field in design_fields}
        if not changes:
            raise HTTPException(status_code=403, detail="Only certificate design settings can be changed")
    for field, document_type in (
        ("certificate_template", "certificate"),
        ("marksheet_template", "marksheet"),
    ):
        if field in changes and changes[field]:
            try:
                changes[field] = sanitize_template(changes[field], document_type=document_type)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "code" in changes and db.scalar(
        select(Branch).where(
            Branch.code == changes["code"],
            Branch.id != branch_id,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="Branch code already exists")

    for field, value in changes.items():
        setattr(branch, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A branch with the submitted unique value already exists",
        ) from None
    db.refresh(branch)
    return branch


@router.post(
    "/{branch_id}/payment-qr",
    response_model=BranchResponse,
    dependencies=[Depends(BranchWrite)],
)
async def upload_payment_qr(
    branch_id: int,
    db: DatabaseSession,
    file: UploadFile = File(...),
    _: object = Depends(SuperAdmin),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    extension = PAYMENT_QR_TYPES.get((file.content_type or "").lower())
    if extension is None:
        raise HTTPException(status_code=400, detail="Upload a JPG, PNG or WebP QR image")
    data = await file.read()
    if not data or len(data) > MAX_PAYMENT_QR_SIZE:
        raise HTTPException(status_code=400, detail="The payment QR image must be 3 MB or smaller")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image") from None
    directory = PAYMENT_QR_DIR / str(branch.id) / "payment"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"upi-qr-{uuid4().hex}{extension}"
    (directory / filename).write_bytes(data)
    branch.upi_qr_code_url = f"/uploads/branches/{branch.id}/payment/{filename}"
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{branch_id}", response_model=BranchResponse, dependencies=[Depends(BranchWrite)])
def deactivate_branch(
    branch_id: int,
    db: DatabaseSession,
    _: object = Depends(SuperAdmin),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    branch.is_active = False
    db.commit()
    db.refresh(branch)
    return branch
