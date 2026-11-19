import unittest
from datetime import date

from app.services.course_lifecycle import (
    add_months,
    enrollment_course_end_date,
    enrollment_course_timing,
)


class _Course:
    duration_months = 6


class _Batch:
    end_date = None
    course = _Course()


class _Enrollment:
    admission_date = date(2026, 9, 26)
    batch = _Batch()


class _ExplodingCourse:
    @property
    def duration_months(self):
        raise AssertionError("batch end date should win over course duration")


class CourseLifecycleTests(unittest.TestCase):
    def test_add_months_clamps_to_shorter_month(self) -> None:
        self.assertEqual(add_months(date(2026, 8, 31), 1), date(2026, 9, 30))
        self.assertEqual(add_months(date(2026, 12, 15), 2), date(2027, 2, 15))

    def test_batch_end_date_wins(self) -> None:
        class Batch(_Batch):
            end_date = date(2027, 3, 31)
            course = type("Course", (), {"duration_months": 6})()

        enrollment = _Enrollment()
        enrollment.batch = Batch()
        self.assertEqual(enrollment_course_end_date(enrollment), date(2027, 3, 31))

    def test_course_duration_fallback(self) -> None:
        enrollment = _Enrollment()
        enrollment.batch = _Batch()
        self.assertEqual(enrollment_course_end_date(enrollment), date(2027, 3, 26))

    def test_timing_reports_remaining_days_and_completion(self) -> None:
        enrollment = _Enrollment()
        enrollment.batch = _Batch()

        end_date, remaining, completed = enrollment_course_timing(
            enrollment, date(2026, 10, 29)
        )
        self.assertEqual(end_date, date(2027, 3, 26))
        self.assertEqual(remaining, 148)
        self.assertFalse(completed)

        _, remaining, completed = enrollment_course_timing(
            enrollment, date(2027, 3, 27)
        )
        self.assertEqual(remaining, -1)
        self.assertTrue(completed)

    def test_unconfigured_course_is_not_completed(self) -> None:
        class Batch(_Batch):
            end_date = None
            course = type("Course", (), {"duration_months": 0})()

        enrollment = _Enrollment()
        enrollment.batch = Batch()
        end_date, remaining, completed = enrollment_course_timing(enrollment)
        self.assertIsNone(end_date)
        self.assertIsNone(remaining)
        self.assertFalse(completed)


if __name__ == "__main__":
    unittest.main()
