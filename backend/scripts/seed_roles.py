from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.role import Role
from app.models.permission import RoleModulePermission

MODULES = (
    "branches", "students", "courses", "staff", "enrollments", "enquiries",
    "fees", "attendance", "examinations", "certificates",
)
DEFAULT_ACCESS = {
    "Super Admin": set(MODULES),
    "Branch Admin": set(MODULES) - {"branches"},
    "Faculty": {"students", "courses", "attendance", "examinations"},
    "Staff": {"students", "courses", "enrollments", "fees", "attendance", "examinations", "certificates"},
    "Counsellor": {"students", "courses", "enrollments", "enquiries"},
    "Student": set(),
}


DEFAULT_ROLES = (
    ("Super Admin", "Full access to the institute management system."),
    ("Branch Admin", "Manages one or more assigned branches."),
    ("Faculty", "Manages classes, attendance, assignments, and examinations."),
    ("Student", "Views courses, fees, attendance, results, and certificates."),
    ("Staff", "Manages assigned institute responsibilities and operational work."),
    ("Counsellor", "Manages student counselling and follow-up responsibilities."),
)


def seed_roles() -> None:
    with SessionLocal() as db:
        for name, description in DEFAULT_ROLES:
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=description)
                db.add(role)
                db.flush()
            for module_key in MODULES:
                permission = db.scalar(select(RoleModulePermission).where(
                    RoleModulePermission.role_id == role.id,
                    RoleModulePermission.module_key == module_key,
                ))
                if permission is None:
                    db.add(RoleModulePermission(
                        role_id=role.id,
                        module_key=module_key,
                        can_access=module_key in DEFAULT_ACCESS[name],
                    ))
        db.commit()
    print("Default roles are ready.")


if __name__ == "__main__":
    seed_roles()
