import unittest
from datetime import date
from types import SimpleNamespace

from app.api.reports import build_student_details
from app.schemas.student import StudentCreate


class _FakeResult:
    def __init__(self, records):
        self.records = records

    def all(self):
        return self.records


class _FakeDb:
    def __init__(self, records):
        self.records = records

    def execute(self, query):
        return _FakeResult(self.records)


class StudentIntakeDetailsTests(unittest.TestCase):
    def test_student_create_accepts_intake_fields(self) -> None:
        payload = StudentCreate(
            full_name="Asha Sharma",
            branch_id=1,
            batch_time="Morning, 9:00–11:00",
            course_name="Diploma in Computer Applications",
            registration_number="REG-2026-001",
            form_number="F-001",
            date_of_joining=date(2026, 11, 25),
        )

        values = payload.model_dump()
        self.assertEqual(values["batch_time"], "Morning, 9:00–11:00")
        self.assertEqual(values["course_name"], "Diploma in Computer Applications")
        self.assertEqual(values["registration_number"], "REG-2026-001")
        self.assertEqual(values["form_number"], "F-001")
        self.assertEqual(values["date_of_joining"], date(2026, 11, 25))

    def test_student_details_report_exposes_intake_fields(self) -> None:
        student = SimpleNamespace(
            full_name="Asha Sharma",
            student_code="STU-2026-00000001",
            registration_number="REG-2026-001",
            form_number="F-001",
            course_name="Diploma in Computer Applications",
            batch_time="Morning, 9:00–11:00",
            date_of_joining=date(2026, 11, 25),
            is_active=True,
        )
        branch = SimpleNamespace(name="Main Branch")
        report = build_student_details(
            db=_FakeDb([(student, branch, "Morning Batch")]),
            branch_id=None,
            faculty_id=None,
        )

        labels = [column["label"] for column in report["columns"]]
        for label in (
            "Registration No.",
            "Form No.",
            "Course Name",
            "Batch Time",
            "Date of Joining",
        ):
            self.assertIn(label, labels)

        row = report["rows"][0]
        self.assertEqual(row["registration_number"], "REG-2026-001")
        self.assertEqual(row["form_number"], "F-001")
        self.assertEqual(row["course"], "Diploma in Computer Applications")
        self.assertEqual(row["batch"], "Morning Batch")
        self.assertEqual(row["batch_time"], "Morning, 9:00–11:00")
        self.assertEqual(row["date_of_joining"], "2026-11-25")


if __name__ == "__main__":
    unittest.main()
