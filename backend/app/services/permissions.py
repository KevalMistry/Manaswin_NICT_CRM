"""Role/module permission defaults and branch-aware effective resolution.

Permissions are layered:

1. Built-in defaults for the role (:data:`DEFAULT_PERMISSIONS`).
2. Optional global overrides (``branch_id IS NULL``), edited by a Super Admin.
3. Optional branch overrides for one branch, edited by that branch's admin.

A branch override wins over a global override, which wins over the built-in
default. Keeping global rows makes the change backwards compatible with the
original single-tenant permission rows.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.permission import RoleModulePermission
from app.models.role import Role


MODULE_LABELS = {
    "branches": "Branches",
    "students": "Students",
    "courses": "Courses & Batches",
    "staff": "Staff & Performance",
    "enrollments": "Enrollments",
    "enquiries": "Enquiries & CRM",
    "fees": "Fees",
    "attendance": "Attendance",
    "examinations": "Examinations",
    "certificates": "Certificates",
    "lms": "Learning (LMS)",
    "notifications": "Notifications & Automation",
    "placement": "Placement Cell",
    "finance": "Finance & Accounts",
    "franchises": "Franchise Management",
    "reports": "Reports",
    "permissions": "Role Permissions",
}

DEFAULT_PERMISSIONS: dict[str, dict[str, bool]] = {
    "Super Admin": {
        "branches": True,
        "students": True,
        "courses": True,
        "staff": True,
        "enrollments": True,
        "enquiries": True,
        "fees": True,
        "attendance": True,
        "examinations": True,
        "certificates": True,
        "lms": True,
        "notifications": True,
        "placement": True,
        "finance": True,
        "franchises": True,
        "reports": True,
        "permissions": True,
    },
    "Branch Admin": {
        "branches": False,
        "students": True,
        "courses": True,
        "staff": True,
        "enrollments": True,
        "enquiries": True,
        "fees": True,
        "attendance": True,
        "examinations": True,
        "certificates": True,
        "lms": True,
        "notifications": True,
        "placement": True,
        "finance": True,
        "franchises": False,
        "reports": True,
        "permissions": True,
    },
    "Faculty": {
        "branches": False,
        "students": True,
        "courses": True,
        "staff": False,
        "enrollments": False,
        "enquiries": False,
        "fees": False,
        "attendance": True,
        "examinations": True,
        "certificates": False,
        "lms": True,
        "notifications": False,
        "placement": True,
        "finance": False,
        "franchises": False,
        "reports": True,
        "permissions": False,
    },
    "Staff": {
        "branches": False,
        "students": True,
        "courses": True,
        "staff": False,
        "enrollments": True,
        "enquiries": False,
        "fees": True,
        "attendance": True,
        "examinations": True,
        "certificates": True,
        "lms": True,
        "notifications": True,
        "placement": True,
        "finance": True,
        "franchises": False,
        "reports": True,
        "permissions": False,
    },
    "Counsellor": {
        "branches": False,
        "students": True,
        "courses": True,
        "staff": False,
        "enrollments": True,
        "enquiries": True,
        "fees": False,
        "attendance": False,
        "examinations": False,
        "certificates": False,
        "lms": False,
        "notifications": False,
        "placement": True,
        "finance": False,
        "franchises": False,
        "reports": True,
        "permissions": False,
    },
    "Student": {
        "branches": False,
        "students": False,
        "courses": False,
        "staff": False,
        "enrollments": False,
        "enquiries": False,
        "fees": False,
        "attendance": False,
        "examinations": False,
        "certificates": False,
        "lms": False,
        "notifications": False,
        "placement": False,
        "finance": False,
        "franchises": False,
        "reports": False,
        "permissions": False,
    },
    "Parent": {},
}


def merge_permission_rows(
    role_name: str,
    rows: Iterable[RoleModulePermission],
    branch_id: int | None,
) -> dict[str, bool]:
    """Merge defaults, global overrides and one branch's overrides.

    ``rows`` may contain permissions for many branches; only global rows and
    rows for ``branch_id`` are considered. Branch rows are applied last so
    they win over global values.
    """
    effective = dict(DEFAULT_PERMISSIONS.get(role_name, {}))
    global_rows: list[RoleModulePermission] = []
    branch_rows: list[RoleModulePermission] = []
    for row in rows:
        if row.branch_id is None:
            global_rows.append(row)
        elif branch_id is not None and row.branch_id == branch_id:
            branch_rows.append(row)
    for row in global_rows:
        effective[row.module_key] = row.can_access
    for row in branch_rows:
        effective[row.module_key] = row.can_access
    return effective


def effective_permission_map(
    db: Session,
    role_id: int,
    role_name: str,
    branch_id: int | None,
) -> dict[str, bool]:
    """Return the effective ``module_key -> can_access`` map for a user."""
    conditions = [RoleModulePermission.role_id == role_id]
    if branch_id is None:
        conditions.append(RoleModulePermission.branch_id.is_(None))
    else:
        conditions.append(
            or_(
                RoleModulePermission.branch_id.is_(None),
                RoleModulePermission.branch_id == branch_id,
            )
        )
    rows = db.scalars(select(RoleModulePermission).where(*conditions)).all()
    return merge_permission_rows(role_name, rows, branch_id)


def ensure_permissions_seeded(db: Session) -> None:
    """Add missing global default rows for active roles.

    Branch-specific rows are not seeded; they inherit the global layer until
    a branch admin saves an override.
    """
    roles = db.scalars(select(Role).where(Role.is_active.is_(True))).all()
    changed = False
    for role in roles:
        defaults = DEFAULT_PERMISSIONS.get(role.name, {})
        existing_keys = set(
            db.scalars(
                select(RoleModulePermission.module_key).where(
                    RoleModulePermission.role_id == role.id,
                    RoleModulePermission.branch_id.is_(None),
                )
            ).all()
        )
        for module_key, default_value in defaults.items():
            if module_key in existing_keys:
                continue
            db.add(
                RoleModulePermission(
                    role_id=role.id,
                    branch_id=None,
                    module_key=module_key,
                    can_access=default_value,
                )
            )
            changed = True
    if changed:
        db.commit()
