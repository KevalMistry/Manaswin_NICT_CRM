from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    require_module,
    require_roles,
)
from app.models.branch import Branch
from app.models.permission import RoleModulePermission
from app.models.role import Role
from app.models.user import User
from app.schemas.permissions import (
    ModulePermission,
    MyPermissionsResponse,
    PermissionUpdate,
    RolePermissionResponse,
)
from app.services.permissions import (
    DEFAULT_PERMISSIONS,
    MODULE_LABELS,
    effective_permission_map,
    ensure_permissions_seeded,
)


router = APIRouter(prefix="/api/permissions", tags=["Permissions"])
PermissionAdmin = require_roles("Super Admin", "Branch Admin")
BRANCH_ADMIN_EDITABLE_ROLES = {"Faculty", "Staff", "Counsellor"}


def _resolve_branch_scope(
    db: DatabaseSession,
    current_user: User,
    branch_id: int | None,
) -> int | None:
    """Return the branch whose permission layer is being read or edited.

    ``None`` means the global layer and is only available to a Super Admin.
    A Branch Admin is always pinned to their own branch, and may not pass a
    different branch id.
    """
    if current_user.role.name == "Super Admin":
        if branch_id is None:
            return None
        if db.get(Branch, branch_id) is None:
            raise HTTPException(status_code=404, detail="Branch not found")
        return branch_id

    if current_user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not assigned to a branch",
        )
    if branch_id is not None and branch_id != current_user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can manage permissions only for your assigned branch",
        )
    return current_user.branch_id


def _branch_name(db: DatabaseSession, branch_id: int | None) -> str | None:
    if branch_id is None:
        return None
    branch = db.get(Branch, branch_id)
    return branch.name if branch else None


def _can_edit_role(role: Role, is_super_admin: bool) -> bool:
    if role.name == "Super Admin":
        return False
    if is_super_admin:
        return True
    return role.name in BRANCH_ADMIN_EDITABLE_ROLES


def _role_permission_response(
    db: DatabaseSession,
    role: Role,
    branch_id: int | None,
    is_super_admin: bool,
) -> RolePermissionResponse:
    effective = effective_permission_map(db, role.id, role.name, branch_id)
    return RolePermissionResponse(
        role_id=role.id,
        role_name=role.name,
        branch_id=branch_id,
        branch_name=_branch_name(db, branch_id),
        can_edit=_can_edit_role(role, is_super_admin),
        permissions=[
            ModulePermission(
                module_key=key,
                label=label,
                can_access=effective.get(key, False),
            )
            for key, label in MODULE_LABELS.items()
        ],
    )


def _permission_row_filter(role_id: int, branch_id: int | None, module_key: str):
    conditions = [
        RoleModulePermission.role_id == role_id,
        RoleModulePermission.module_key == module_key,
    ]
    if branch_id is None:
        conditions.append(RoleModulePermission.branch_id.is_(None))
    else:
        conditions.append(RoleModulePermission.branch_id == branch_id)
    return conditions


def _upsert_permission(
    db: DatabaseSession,
    role_id: int,
    branch_id: int | None,
    module_key: str,
    can_access: bool,
) -> None:
    permission = db.scalar(
        select(RoleModulePermission).where(
            *_permission_row_filter(role_id, branch_id, module_key)
        )
    )
    if permission is None:
        permission = RoleModulePermission(
            role_id=role_id,
            branch_id=branch_id,
            module_key=module_key,
        )
        db.add(permission)
    permission.can_access = can_access


def _enforce_role_edit_scope(role: Role, current_user: User) -> bool:
    """Validate that ``current_user`` may edit ``role`` and return admin flag."""
    is_super_admin = current_user.role.name == "Super Admin"
    if not is_super_admin and role.name not in BRANCH_ADMIN_EDITABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Branch Admins can only customize permissions for: "
                f"{', '.join(sorted(BRANCH_ADMIN_EDITABLE_ROLES))}."
            ),
        )
    if is_super_admin and role.name == "Super Admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Super Admin has permanent full access to all modules and "
                "cannot be modified."
            ),
        )
    return is_super_admin


@router.get("/my-permissions", response_model=MyPermissionsResponse)
def get_my_permissions(
    db: DatabaseSession,
    current_user: User = Depends(
        require_roles(
            "Super Admin",
            "Branch Admin",
            "Faculty",
            "Staff",
            "Counsellor",
            "Student",
        )
    ),
) -> MyPermissionsResponse:
    if current_user.role.name == "Super Admin":
        return MyPermissionsResponse(
            role_name=current_user.role.name,
            role_id=current_user.role_id,
            branch_id=current_user.branch_id,
            branch_name=_branch_name(db, current_user.branch_id),
            can_manage_permissions=True,
            allowed_modules=list(MODULE_LABELS.keys()),
        )

    ensure_permissions_seeded(db)
    effective = effective_permission_map(
        db,
        current_user.role_id,
        current_user.role.name,
        current_user.branch_id,
    )
    allowed = [key for key in MODULE_LABELS if effective.get(key, False)]

    return MyPermissionsResponse(
        role_name=current_user.role.name,
        role_id=current_user.role_id,
        branch_id=current_user.branch_id,
        branch_name=_branch_name(db, current_user.branch_id),
        can_manage_permissions=(
            current_user.role.name in {"Super Admin", "Branch Admin"}
            and effective.get("permissions", False)
        ),
        allowed_modules=allowed,
    )


@router.get(
    "",
    response_model=list[RolePermissionResponse],
    dependencies=[Depends(require_module("permissions"))],
)
def list_permissions(
    db: DatabaseSession,
    current_user: User = Depends(PermissionAdmin),
    branch_id: int | None = Query(default=None),
) -> list[RolePermissionResponse]:
    ensure_permissions_seeded(db)
    scope = _resolve_branch_scope(db, current_user, branch_id)
    roles = db.scalars(
        select(Role).where(Role.is_active.is_(True)).order_by(Role.id)
    ).all()
    is_super_admin = current_user.role.name == "Super Admin"
    return [
        _role_permission_response(db, role, scope, is_super_admin) for role in roles
    ]


@router.put(
    "/{role_id}",
    response_model=RolePermissionResponse,
    dependencies=[Depends(require_module("permissions"))],
)
def update_permissions(
    role_id: int,
    payload: PermissionUpdate,
    db: DatabaseSession,
    current_user: User = Depends(PermissionAdmin),
    branch_id: int | None = Query(default=None),
) -> RolePermissionResponse:
    role = db.get(Role, role_id)
    if role is None or not role.is_active:
        raise HTTPException(status_code=404, detail="Role not found")

    scope = _resolve_branch_scope(db, current_user, branch_id)
    is_super_admin = _enforce_role_edit_scope(role, current_user)

    unknown = set(payload.permissions) - set(MODULE_LABELS)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown module key: {next(iter(unknown))}"
        )

    if not is_super_admin:
        # A Branch Admin may only hand out modules they can already use in
        # their own branch. Otherwise they could grant themselves (via a role
        # they are allowed to edit) access to branches, franchises, etc.
        #
        # Values already inherited from the global layer are not a new grant,
        # so they may be written back unchanged even when the branch admin
        # does not personally have that module.
        admin_effective = effective_permission_map(
            db,
            current_user.role_id,
            current_user.role.name,
            current_user.branch_id,
        )
        current_role_effective = effective_permission_map(
            db, role.id, role.name, scope
        )
        escalated = sorted(
            key
            for key, can_access in payload.permissions.items()
            if can_access
            and not current_role_effective.get(key, False)
            and not admin_effective.get(key, False)
        )
        if escalated:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Branch Admins cannot grant modules they do not have access "
                    f"to: {', '.join(escalated)}"
                ),
            )

    for module_key, can_access in payload.permissions.items():
        _upsert_permission(db, role_id, scope, module_key, can_access)

    record_audit(
        db,
        current_user.id,
        "permissions_updated",
        "role_permissions",
        role.id,
        {
            "role_name": role.name,
            "branch_id": scope,
            "branch_name": _branch_name(db, scope),
            "updated_by": current_user.email,
            "permissions": payload.permissions,
        },
    )
    db.commit()
    return _role_permission_response(db, role, scope, is_super_admin)


@router.post(
    "/{role_id}/reset",
    response_model=RolePermissionResponse,
    dependencies=[Depends(require_module("permissions"))],
)
def reset_role_permissions(
    role_id: int,
    db: DatabaseSession,
    current_user: User = Depends(PermissionAdmin),
    branch_id: int | None = Query(default=None),
) -> RolePermissionResponse:
    role = db.get(Role, role_id)
    if role is None or not role.is_active:
        raise HTTPException(status_code=404, detail="Role not found")

    scope = _resolve_branch_scope(db, current_user, branch_id)
    is_super_admin = _enforce_role_edit_scope(role, current_user)

    if scope is None:
        # Global reset restores the built-in defaults. Branch admins never
        # reach this path because their scope is always a branch id.
        defaults = DEFAULT_PERMISSIONS.get(role.name, {})
        for module_key in MODULE_LABELS:
            _upsert_permission(
                db,
                role_id,
                None,
                module_key,
                defaults.get(module_key, False),
            )
        reset_kind = "global_defaults"
    else:
        # Branch reset removes that branch's overrides, so the branch falls
        # back to the global layer (which may itself be Super Admin-customised).
        rows = db.scalars(
            select(RoleModulePermission).where(
                RoleModulePermission.role_id == role_id,
                RoleModulePermission.branch_id == scope,
            )
        ).all()
        for row in rows:
            db.delete(row)
        reset_kind = "inherited_global"

    record_audit(
        db,
        current_user.id,
        "permissions_reset_to_default",
        "role_permissions",
        role.id,
        {
            "role_name": role.name,
            "branch_id": scope,
            "branch_name": _branch_name(db, scope),
            "reset_kind": reset_kind,
            "reset_by": current_user.email,
        },
    )
    db.commit()
    return _role_permission_response(db, role, scope, is_super_admin)
