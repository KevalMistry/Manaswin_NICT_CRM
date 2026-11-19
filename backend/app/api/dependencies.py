from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DatabaseSession,
) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_value = int(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id_value)
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or does not exist",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    def role_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_dependency


def check_branch_access(current_user: User, branch_id: int | None) -> None:
    """Reject access to records outside the user's assigned branch.

    Super Admin is the only role that works across branches. Every other role
    with a branch assignment is confined to that branch. A non-admin account
    without a branch assignment is rejected rather than silently seeing every
    branch.
    """
    if current_user.role.name == "Super Admin":
        return
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not assigned to a branch",
        )
    if branch_id is not None and branch_id != current_user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can access only your assigned branch",
        )


def branch_scope(current_user: User) -> int | None:
    """Return the branch id that list queries must be filtered by.

    ``None`` means no filter (Super Admin). Non-admin users without a branch
    assignment are rejected.
    """
    if current_user.role.name == "Super Admin":
        return None
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not assigned to a branch",
        )
    return current_user.branch_id


def has_module_access(
    current_user: User,
    db: Session,
    *module_keys: str,
) -> bool:
    """Return whether the user's role grants at least one module key.

    Shared by the ``require_module`` dependency and by endpoints that also need
    to allow a separate principal, such as a student opening their own
    certificate while staff open documents through the certificates module.
    """
    if current_user.role.name == "Super Admin":
        return True
    if not module_keys:
        return False

    from app.services.permissions import effective_permission_map

    effective = effective_permission_map(
        db,
        current_user.role_id,
        current_user.role.name,
        current_user.branch_id,
    )
    return any(effective.get(key, False) for key in module_keys)


def require_module(*module_keys: str) -> Callable:
    """Require access to at least one of the given modules.

    Multiple keys are useful for shared reference data. For example, the
    attendance page needs to read students, enrollments and batches, but those
    records belong to other modules. The page itself is still protected by the
    'attendance' module, while the shared reads accept any module that
    legitimately needs them.
    """
    if not module_keys:
        raise ValueError("At least one module key is required")

    def module_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
        db: DatabaseSession,
    ) -> User:
        if has_module_access(current_user, db, *module_keys):
            return current_user

        requested = " or ".join(f"'{key}'" for key in module_keys)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your role ({current_user.role.name}) does not have permission "
                f"to access the {requested} module."
            ),
        )

    return module_dependency
