import unittest
from datetime import date

from pydantic import ValidationError

from app.schemas.attendance import AttendanceSessionCreate
from app.schemas.course import CourseCreate
from app.schemas.fee import FeePlanCreate, InstallmentCreate


class SchemaTests(unittest.TestCase):
    def test_fee_installments_are_required_and_positive(self) -> None:
        payload = FeePlanCreate(
            enrollment_id=1,
            total_amount="1000",
            installments=[
                InstallmentCreate(
                    installment_number=1,
                    amount="1000",
                    due_date=date(2026, 11, 1),
                )
            ],
        )

        self.assertEqual(payload.installments[0].amount, 1000)

        with self.assertRaises(ValidationError):
            InstallmentCreate(
                installment_number=1,
                amount="0",
                due_date=date(2026, 11, 1),
            )

    def test_course_fee_is_optional_and_non_negative(self) -> None:
        course = CourseCreate(
            name="Full Stack Python",
            code="PYTHON-02",
            duration_months=6,
        )
        self.assertIsNone(course.fee_amount)

        course = CourseCreate(
            name="Full Stack Python",
            code="PYTHON-02",
            duration_months=6,
            fee_amount="60000.00",
        )
        self.assertEqual(course.fee_amount, 60000)

        with self.assertRaises(ValidationError):
            CourseCreate(
                name="Full Stack Python",
                code="PYTHON-02",
                duration_months=6,
                fee_amount="-1",
            )

    def test_qr_session_expiry_is_bounded(self) -> None:
        self.assertEqual(
            AttendanceSessionCreate(
                batch_id=1,
                attendance_date=date(2026, 10, 25),
                expires_in_minutes=10,
            ).expires_in_minutes,
            10,
        )

        with self.assertRaises(ValidationError):
            AttendanceSessionCreate(
                batch_id=1,
                attendance_date=date(2026, 10, 25),
                expires_in_minutes=31,
            )


if __name__ == "__main__":
    unittest.main()
