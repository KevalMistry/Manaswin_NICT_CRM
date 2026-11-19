from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession, get_current_user
from app.core.ratelimit import rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import FRONTEND_URL, SMTP_FROM, SMTP_HOST
from app.models.role import Role
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    TokenResponse,
    UserCreate,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.services.email_templates import EmailTemplateError, send_templated_email
from app.services.mailer import MailDeliveryError, MailNotConfigured


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
PROFILE_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "profiles"
MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


@router.post("/register", response_model=UserResponse, status_code=201)
def register_user(payload: UserCreate, db: DatabaseSession) -> User:
    if db.scalar(select(User.id)) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled after initial setup",
        )

    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")

    if db.get(Role, payload.role_id) is None:
        raise HTTPException(status_code=400, detail="Role does not exist")

    if payload.branch_id is not None:
        from app.models.branch import Branch

        if db.get(Branch, payload.branch_id) is None:
            raise HTTPException(status_code=400, detail="Branch does not exist")

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        phone=payload.phone,
        role_id=payload.role_id,
        branch_id=payload.branch_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", 10, 300))])
def login(payload: LoginRequest, db: DatabaseSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    if user.role.name == "Parent":
        raise HTTPException(
            status_code=403,
            detail="Parent accounts no longer sign in separately. Use the linked student's account.",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        user=user,
    )


@router.post("/forgot-password", dependencies=[Depends(rate_limit("forgot", 5, 900))])
def forgot_password(payload: ForgotPasswordRequest, db: DatabaseSession) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    response = {"message": "If an active account exists for that email, a password reset link has been sent."}
    if user is None:
        return response
    if not all((SMTP_HOST, SMTP_FROM)):
        raise HTTPException(status_code=503, detail="Password reset email is not configured. Contact the system administrator.")

    raw_token = secrets.token_urlsafe(48)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30),
    )
    db.add(token)
    db.commit()
    reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
    try:
        send_templated_email(
            db,
            key="password_reset",
            recipient=user.email,
            context={
                "user_name": user.full_name,
                "reset_link": reset_url,
                "expires_minutes": 30,
            },
            branch_id=user.branch_id,
            category="password_reset",
            triggered_by_id=user.id,
        )
        db.commit()
    except (
        EmailTemplateError,
        MailNotConfigured,
        MailDeliveryError,
    ) as error:
        db.rollback()
        db.delete(token)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="The reset email could not be sent. Try again later.",
        ) from error
    return response


@router.post("/reset-password", dependencies=[Depends(rate_limit("reset", 10, 900))])
def reset_password(payload: ResetPasswordRequest, db: DatabaseSession) -> dict[str, str]:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    reset_token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if reset_token is None or reset_token.used_at is not None or reset_token.expires_at <= now:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or expired.")
    user = db.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or expired.")
    user.hashed_password = hash_password(payload.new_password)
    reset_token.used_at = now
    db.commit()
    return {"message": "Password reset successfully. You can now sign in."}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdate,
    db: DatabaseSession,
    current_user: User = Depends(get_current_user),
) -> User:
    current_user.full_name = payload.full_name
    current_user.phone = payload.phone
    current_user.profile_photo_url = payload.profile_photo_url
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/profile-photo", response_model=UserResponse)
async def upload_profile_photo(
    db: DatabaseSession,
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
) -> User:
    extension = ALLOWED_PROFILE_PHOTO_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG, GIF, and WebP images are allowed",
        )

    contents = await file.read(MAX_PROFILE_PHOTO_SIZE + 1)
    if len(contents) > MAX_PROFILE_PHOTO_SIZE:
        raise HTTPException(status_code=413, detail="Profile photo must be 5 MB or smaller")

    signatures = {
        "image/jpeg": contents.startswith(b"\xff\xd8\xff"),
        "image/png": contents.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": contents.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": contents.startswith(b"RIFF") and contents[8:12] == b"WEBP",
    }
    if not signatures[file.content_type]:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image")

    PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"user-{current_user.id}-{uuid4().hex}{extension}"
    destination = PROFILE_UPLOAD_DIR / filename
    destination.write_bytes(contents)

    old_photo = current_user.profile_photo_url
    current_user.profile_photo_url = f"/uploads/profiles/{filename}"
    db.commit()
    db.refresh(current_user)

    if old_photo and old_photo.startswith("/uploads/profiles/"):
        old_file = PROFILE_UPLOAD_DIR / Path(old_photo).name
        if old_file != destination and old_file.is_file():
            old_file.unlink()

    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: DatabaseSession,
    current_user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
