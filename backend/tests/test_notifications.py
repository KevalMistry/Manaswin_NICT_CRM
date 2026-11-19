import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.notifications import run_notification_jobs
from app.schemas.notification import NotificationRunRequest
from app.services.notifications import (
    PlannedNotification,
    _completion_message,
    _fee_message,
    _installment_status,
    deliver_notifications,
)


def _payment(amount: str) -> SimpleNamespace:
    return SimpleNamespace(amount=Decimal(amount))


def _installment(
    number: int, amount: str, due: date, payments: list[SimpleNamespace] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        installment_number=number,
        amount=Decimal(amount),
        due_date=due,
        payments=payments or [],
    )


def _fee_group(installments: list[SimpleNamespace]) -> SimpleNamespace:
    student = SimpleNamespace(id=3, full_name="Aarav Mehta", email="aarav@example.com")
    batch = SimpleNamespace(
        name="Python October 2026",
        course=SimpleNamespace(name="Full Stack Python"),
        branch=SimpleNamespace(name="Manaswin NICT Vapi", id=1),
    )
    enrollment = SimpleNamespace(id=2, student=student, batch=batch)
    return SimpleNamespace(enrollment=enrollment, student=student, installments=installments)


class NotificationPlanTests(unittest.TestCase):
    def test_installment_status_marks_overdue_today_and_soon(self) -> None:
        today = date(2026, 10, 29)

        self.assertEqual(_installment_status(date(2026, 10, 27), today), "Overdue")
        self.assertEqual(_installment_status(today, today), "Due today")
        self.assertEqual(_installment_status(date(2026, 11, 2), today), "Due soon")

    def test_fee_message_totals_only_outstanding_amounts(self) -> None:
        group = _fee_group(
            [
                _installment(1, "20000.00", date(2026, 10, 20), [_payment("5000.00")]),
                _installment(2, "15000.00", date(2026, 11, 1)),
            ]
        )

        subject, message = _fee_message(group, date(2026, 10, 29))

        self.assertIn("Manaswin NICT Vapi", subject)
        self.assertIn("Aarav Mehta", message)
        self.assertIn("instalment 1: INR 15,000.00", message)
        self.assertIn("instalment 2: INR 15,000.00", message)
        self.assertIn("Total pending: INR 30,000.00", message)
        self.assertIn("overdue", message.lower())
        self.assertIn("due soon", message.lower())

    def test_completion_message_mentions_course_and_checks(self) -> None:
        student = SimpleNamespace(full_name="Diya Shah")
        batch = SimpleNamespace(
            name="Data Analytics October 2026",
            course=SimpleNamespace(name="Data Analytics"),
            branch=SimpleNamespace(name="Manaswin NICT Vapi"),
        )
        enrollment = SimpleNamespace(student=student, batch=batch)

        subject, message = _completion_message(enrollment, date(2026, 10, 29))

        self.assertIn("Data Analytics course completion", subject)
        self.assertIn("2026-10-29", message)
        self.assertIn("Diya Shah", message)
        self.assertIn("online exams", message)

    def test_dry_run_marks_ready_plans_without_persisting(self) -> None:
        ready = PlannedNotification(
            category="fee_reminder",
            channel="email",
            student_id=1,
            student_name="A",
            enrollment_id=1,
            branch_id=1,
            recipient="a@example.com",
            subject="S",
            message="M",
        )
        skipped = PlannedNotification(
            category="fee_reminder",
            channel="whatsapp",
            student_id=1,
            student_name="A",
            enrollment_id=1,
            branch_id=1,
            recipient=None,
            subject=None,
            message="M",
            status="skipped",
            detail="no phone",
        )

        # A dry run must never touch the database, so passing None is safe.
        deliver_notifications(None, [ready, skipped], dry_run=True)  # type: ignore[arg-type]

        self.assertEqual(ready.status, "dry_run")
        self.assertEqual(skipped.status, "skipped")
        self.assertEqual(skipped.detail, "no phone")


class NotificationRequestTests(unittest.TestCase):
    def test_run_request_defaults_to_dry_run_without_live_confirmation(self) -> None:
        payload = NotificationRunRequest()

        self.assertTrue(payload.dry_run)
        self.assertFalse(payload.confirm_live)
        self.assertEqual(payload.channels, ["email"])
        self.assertIn("fee_reminder", payload.categories)

    def test_unknown_channel_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            NotificationRunRequest(channels=["sms"])  # type: ignore[list-item]

    def test_live_run_requires_explicit_confirmation(self) -> None:
        payload = NotificationRunRequest(dry_run=False, confirm_live=False)

        with self.assertRaises(HTTPException) as raised:
            # The guard runs before the payload touches the database.
            run_notification_jobs(payload, None, None)  # type: ignore[arg-type]

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("confirm_live", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
