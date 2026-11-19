"""Prepare a clean production database and create the first Super Admin.

Usage:
    cd backend
    .venv/bin/python scripts/prepare_production.py --reset
    .venv/bin/python scripts/prepare_production.py --create-super-admin

Combine both to wipe demo data and bootstrap the first account:
    .venv/bin/python scripts/prepare_production.py --reset --create-super-admin
"""
from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select, text

from app.core.security import hash_password
from app.db.database import SessionLocal, db_engine as engine
from app.db.base import Base
from app.models.branch import Branch
from app.models.role import Role
from app.models.user import User
from app.services.permissions import ensure_permissions_seeded

ALL_ROLES = (
    ("Super Admin", "Full access to the institute management system."),
    ("Branch Admin", "Manages one or more assigned branches."),
    ("Faculty", "Manages classes, attendance, assignments, and examinations."),
    ("Staff", "Manages assigned institute responsibilities and operational work."),
    ("Counsellor", "Manages student counselling and follow-up responsibilities."),
    ("Student", "Views courses, fees, attendance, results, and certificates."),
    ("Parent", "Read-only access to a linked student's progress."),
)

KEEP_TABLES = {"roles", "role_module_permissions", "alembic_version"}


def ensure_roles(db) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name, description in ALL_ROLES:
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=description)
            db.add(role)
            db.flush()
        roles[name] = role
    db.commit()
    return roles


def reset_data() -> None:
    keep = KEEP_TABLES
    tables = [t for t in Base.metadata.sorted_tables if t.name not in keep]
    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "mysql":
            connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        elif dialect == "mssql":
            for table in tables:
                connection.execute(text(f"ALTER TABLE [{table.name}] NOCHECK CONSTRAINT ALL"))
        elif dialect == "sqlite":
            connection.execute(text("PRAGMA foreign_keys=OFF"))

        for table in reversed(tables):
            connection.execute(table.delete())

        if dialect == "mysql":
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        elif dialect == "mssql":
            for table in tables:
                connection.execute(text(f"ALTER TABLE [{table.name}] WITH CHECK CHECK CONSTRAINT ALL"))
        elif dialect == "sqlite":
            connection.execute(text("PRAGMA foreign_keys=ON"))
    print(f"Cleared {len(tables)} tables. Roles/permissions kept.")


def create_super_admin(db) -> None:
    ensure_roles(db)
    ensure_permissions_seeded(db)

    full_name = input("Full name: ").strip()
    email = input("Email: ").strip().lower()
    phone = input("Phone (optional): ").strip() or None
    branch_input = input("Branch ID (optional, leave blank for none): ").strip()
    branch_id = int(branch_input) if branch_input else None
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise SystemExit(f"A user with email {email} already exists.")

    roles = ensure_roles(db)
    super_admin_role = roles["Super Admin"]

    if branch_id is not None:
        if db.get(Branch, branch_id) is None:
            raise SystemExit(f"Branch {branch_id} does not exist.")

    user = User(
        full_name=full_name,
        email=email,
        phone=phone,
        role_id=super_admin_role.id,
        branch_id=branch_id,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Super Admin created: id={user.id}, email={user.email}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Truncate all demo/operational data.")
    parser.add_argument(
        "--create-super-admin", action="store_true", help="Interactively create a Super Admin account."
    )
    args = parser.parse_args()

    if args.reset:
        reset_data()

    if args.create_super_admin:
        with SessionLocal() as db:
            create_super_admin(db)

    if not args.reset and not args.create_super_admin:
        parser.print_help()


if __name__ == "__main__":
    main()
