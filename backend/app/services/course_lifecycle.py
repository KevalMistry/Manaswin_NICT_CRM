"""Course duration and enrollment completion helpers.

A course is time-boxed (for example 3, 4 or 6 months). The date on which a
student finishes a course is derived from the batch they joined:

* an explicit batch end date wins, because a branch may run a shorter or
  longer cohort than the catalogue duration;
* otherwise the course duration in months is added to the admission date.

Keeping this in one place means enrollment lists, certificate eligibility and
the automatic certificate sweep always agree on when a course ends.
"""

from __future__ import annotations

import calendar
from datetime import date


def add_months(value: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def enrollment_course_end_date(enrollment) -> date | None:
    """Return the date the enrollment's course is scheduled to finish."""
    batch = getattr(enrollment, "batch", None)
    if batch is None:
        return None
    if batch.end_date is not None:
        return batch.end_date
    course = getattr(batch, "course", None)
    duration = getattr(course, "duration_months", None)
    if not duration:
        return None
    return add_months(enrollment.admission_date, int(duration))


def enrollment_course_timing(
    enrollment,
    today: date | None = None,
) -> tuple[date | None, int | None, bool]:
    """Return ``(end_date, days_remaining, course_completed)``.

    ``days_remaining`` is negative once the end date has passed. A missing end
    date is treated as not completed so certificates are never issued for an
    unconfigured course by accident.
    """
    today = today or date.today()
    end_date = enrollment_course_end_date(enrollment)
    if end_date is None:
        return None, None, False
    remaining = (end_date - today).days
    return end_date, remaining, remaining <= 0
