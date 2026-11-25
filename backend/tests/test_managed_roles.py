import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.staff import list_managed_roles
from app.models.role import Role


def _current_user(role_name: str) -> SimpleNamespace:
    return SimpleNamespace(role=SimpleNamespace(name=role_name))


def _role(id: int, name: str) -> Role:
    return Role(id=id, name=name, description=None, is_active=True)


class ManagedRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Role.__table__.create(self.engine)
        self.db = Session(self.engine)
        # Deliberately shifted IDs: installations do not share these numbers.
        self.db.add_all(
            [
                _role(1, "Parent"),
                _role(2, "Super Admin"),
                _role(3, "Branch Admin"),
                _role(4, "Faculty"),
                _role(5, "Student"),
                _role(6, "Staff"),
                _role(7, "Counsellor"),
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_roles_use_database_ids_not_hardcoded_numbers(self) -> None:
        roles = list_managed_roles(
            db=self.db,
            current_user=_current_user("Super Admin"),
        )

        self.assertEqual(
            [(role.id, role.name) for role in roles],
            [
                (3, "Branch Admin"),
                (4, "Faculty"),
                (6, "Staff"),
                (7, "Counsellor"),
            ],
        )

    def test_branch_admin_cannot_manage_branch_admins(self) -> None:
        roles = list_managed_roles(
            db=self.db,
            current_user=_current_user("Branch Admin"),
        )

        self.assertEqual(
            [(role.id, role.name) for role in roles],
            [(4, "Faculty"), (6, "Staff"), (7, "Counsellor")],
        )


if __name__ == "__main__":
    unittest.main()
