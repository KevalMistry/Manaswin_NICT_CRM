"""Shared analytics helpers for dashboards and the reports module.

Every function accepts an optional ``branch_id`` (``None`` means all branches,
which only the Super Admin may request) and, where relevant, a ``faculty_id``
so a faculty member only sees the batches assigned to them.

The return values are plain JSON-ready dictionaries so the same data can power
both the role dashboards and the downloadable reports.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment


ENQUIRY_STATUS_LABELS = {
    "new_lead": "New Lead",
    "follow_up": "Follow Up",
    "demo": "Demo",
    "counselling": "Counselling",
    "admitted": "Admitted",
    "lost": "Lost",
}
ENQUIRY_STATUS_ORDER = tuple(ENQUIRY_STATUS_LABELS)

ENQUIRY_SOURCE_LABELS = {
    "walk_in": "Walk-in",
    "online": "Online",
    "website": "Website",
    "whatsapp": "WhatsApp",
    "facebook": "Facebook",
    "google_ads": "Google Ads",
    "referral": "Referral",
    "other": "Other",
}

GRADE_ORDER = ("A+", "A", "B+", "B", "C", "D", "F")

PAYMENT_METHOD_LABELS = {
    "cash": "Cash",
    "bank_transfer": "Bank Transfer",
    "upi": "UPI",
    "card": "Card",
    "cheque": "Cheque",
}


def chart(
    chart_type: str,
    labels: list[str],
    series: list[dict],
    value_format: str = "number",
) -> dict:
    return {
        "type": chart_type,
        "labels": labels,
        "series": series,
        "value_format": value_format,
    }


def month_windows(months: int, today: date | None = None) -> list[tuple[date, date, str]]:
    """Return the last ``months`` calendar months as (start, end, label)."""
    today = today or date.today()
    windows: list[tuple[date, date, str]] = []
    year, month = today.year, today.month
    for offset in range(months - 1, -1, -1):
        target_month = month - offset
        target_year = year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        start = date(target_year, target_month, 1)
        end = date(target_year, target_month, monthrange(target_year, target_month)[1])
        windows.append((start, end, start.strftime("%b %y")))
    return windows


def week_windows(weeks: int, today: date | None = None) -> list[tuple[date, date, str]]:
    today = today or date.today()
    windows: list[tuple[date, date, str]] = []
    for offset in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * offset)
        start = end - timedelta(days=6)
        windows.append((start, end, start.strftime("%d %b")))
    return windows


def _branch_filter(query, branch_id: int | None, column):
    if branch_id is not None:
        query = query.where(column == branch_id)
    return query


def monthly_admissions(
    db: Session,
    months: int = 6,
    branch_id: int | None = None,
    faculty_id: int | None = None,
) -> dict:
    windows = month_windows(months)
    labels: list[str] = []
    counts: list[int] = []
    for start, end, label in windows:
        query = (
            select(func.count(Enrollment.id))
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Enrollment.admission_date >= start, Enrollment.admission_date <= end)
        )
        query = _branch_filter(query, branch_id, Batch.branch_id)
        if faculty_id is not None:
            query = query.where(Batch.faculty_id == faculty_id)
        labels.append(label)
        counts.append(int(db.scalar(query) or 0))
    return chart("bar", labels, [{"name": "Admissions", "data": counts}])


def monthly_revenue(
    db: Session,
    months: int = 6,
    branch_id: int | None = None,
) -> dict:
    windows = month_windows(months)
    labels: list[str] = []
    amounts: list[float] = []
    for start, end, label in windows:
        query = (
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
            .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
            .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Payment.payment_date >= start, Payment.payment_date <= end)
        )
        query = _branch_filter(query, branch_id, Batch.branch_id)
        labels.append(label)
        amounts.append(float(db.scalar(query) or 0))
    return chart("line", labels, [{"name": "Collected", "data": amounts}], "currency")


def course_popularity(
    db: Session,
    branch_id: int | None = None,
    faculty_id: int | None = None,
    limit: int = 6,
) -> dict:
    query = (
        select(Course.name, func.count(Enrollment.id))
        .join(Batch, Batch.course_id == Course.id)
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .where(Enrollment.status != "cancelled")
        .group_by(Course.id, Course.name)
        .order_by(func.count(Enrollment.id).desc(), Course.name)
        .limit(limit)
    )
    query = _branch_filter(query, branch_id, Batch.branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    rows = db.execute(query).all()
    return chart(
        "hbar",
        [row[0] for row in rows],
        [{"name": "Enrollments", "data": [int(row[1]) for row in rows]}],
    )


def fee_aging(db: Session, branch_id: int | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    paid_subquery = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.installment_id == FeeInstallment.id)
        .scalar_subquery()
    )
    query = (
        select(FeeInstallment.due_date, FeeInstallment.amount, paid_subquery)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Enrollment.status != "cancelled")
    )
    query = _branch_filter(query, branch_id, Batch.branch_id)
    rows = db.execute(query).all()

    labels = ["Current", "1–30 days", "31–60 days", "61–90 days", "90+ days"]
    totals = [0.0, 0.0, 0.0, 0.0, 0.0]
    for due_date, amount, paid in rows:
        remaining = float(Decimal(amount) - Decimal(paid or 0))
        if remaining <= 0:
            continue
        days = (today - due_date).days
        if days <= 0:
            totals[0] += remaining
        elif days <= 30:
            totals[1] += remaining
        elif days <= 60:
            totals[2] += remaining
        elif days <= 90:
            totals[3] += remaining
        else:
            totals[4] += remaining
    return chart("donut", labels, [{"name": "Outstanding", "data": totals}], "currency")


def attendance_trend(
    db: Session,
    weeks: int = 6,
    branch_id: int | None = None,
    faculty_id: int | None = None,
    today: date | None = None,
) -> dict:
    labels: list[str] = []
    rates: list[float] = []
    for start, end, label in week_windows(weeks, today):
        query = (
            select(
                func.count(Attendance.id),
                func.sum(case((Attendance.status.in_(("present", "late")), 1), else_=0)),
            )
            .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Attendance.attendance_date >= start, Attendance.attendance_date <= end)
        )
        query = _branch_filter(query, branch_id, Batch.branch_id)
        if faculty_id is not None:
            query = query.where(Batch.faculty_id == faculty_id)
        total, attended = db.execute(query).one()
        total = int(total or 0)
        attended = int(attended or 0)
        labels.append(label)
        rates.append(round((attended / total) * 100, 1) if total else 0.0)
    return chart("line", labels, [{"name": "Attendance", "data": rates}], "percent")


def payment_method_split(
    db: Session,
    branch_id: int | None = None,
    months: int = 6,
) -> dict:
    windows = month_windows(months)
    start = windows[0][0]
    query = (
        select(Payment.payment_method, func.coalesce(func.sum(Payment.amount), 0))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Payment.payment_date >= start)
        .group_by(Payment.payment_method)
        .order_by(func.sum(Payment.amount).desc())
    )
    query = _branch_filter(query, branch_id, Batch.branch_id)
    rows = db.execute(query).all()
    return chart(
        "donut",
        [PAYMENT_METHOD_LABELS.get(row[0], row[0].replace("_", " ").title()) for row in rows],
        [{"name": "Collected", "data": [float(row[1]) for row in rows]}],
        "currency",
    )


def enquiry_funnel(db: Session, branch_id: int | None = None) -> dict:
    query = select(Enquiry.status, func.count(Enquiry.id))
    query = _branch_filter(query, branch_id, Enquiry.branch_id)
    rows = dict(db.execute(query.group_by(Enquiry.status)).all())
    labels = [ENQUIRY_STATUS_LABELS[status] for status in ENQUIRY_STATUS_ORDER]
    values = [int(rows.get(status, 0)) for status in ENQUIRY_STATUS_ORDER]
    return chart("hbar", labels, [{"name": "Enquiries", "data": values}])


def enquiry_sources(db: Session, branch_id: int | None = None) -> dict:
    query = select(Enquiry.source, func.count(Enquiry.id))
    query = _branch_filter(query, branch_id, Enquiry.branch_id)
    rows = db.execute(query.group_by(Enquiry.source).order_by(func.count(Enquiry.id).desc())).all()
    return chart(
        "donut",
        [ENQUIRY_SOURCE_LABELS.get(row[0], row[0].replace("_", " ").title()) for row in rows],
        [{"name": "Leads", "data": [int(row[1]) for row in rows]}],
    )


def exam_grade_distribution(
    db: Session,
    branch_id: int | None = None,
    faculty_id: int | None = None,
) -> dict:
    query = (
        select(ExamMark.grade, func.count(ExamMark.id))
        .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
        .join(Examination, ExamSubject.examination_id == Examination.id)
        .join(Batch, Examination.batch_id == Batch.id)
        .where(Examination.is_published.is_(True))
    )
    query = _branch_filter(query, branch_id, Batch.branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    rows = dict(db.execute(query.group_by(ExamMark.grade)).all())
    labels = [grade for grade in GRADE_ORDER if rows.get(grade)]
    if not labels and rows:
        labels = sorted(rows)
    return chart(
        "bar",
        labels,
        [{"name": "Results", "data": [int(rows.get(grade, 0)) for grade in labels]}],
    )


def batch_students(
    db: Session,
    branch_id: int | None = None,
    faculty_id: int | None = None,
    limit: int = 6,
) -> dict:
    query = (
        select(Batch.name, func.count(Enrollment.id))
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .where(Batch.is_active.is_(True), Enrollment.status == "active")
        .group_by(Batch.id, Batch.name)
        .order_by(func.count(Enrollment.id).desc(), Batch.name)
        .limit(limit)
    )
    query = _branch_filter(query, branch_id, Batch.branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    rows = db.execute(query).all()
    return chart(
        "hbar",
        [row[0] for row in rows],
        [{"name": "Students", "data": [int(row[1]) for row in rows]}],
    )


def total_outstanding(db: Session, branch_id: int | None = None) -> float:
    aging = fee_aging(db, branch_id)
    return float(sum(aging["series"][0]["data"]))


def branch_revenue(db: Session, branches: list[dict]) -> dict:
    ordered = sorted(branches, key=lambda item: item["monthly_revenue"], reverse=True)
    return chart(
        "hbar",
        [item["name"] for item in ordered],
        [{"name": "This month", "data": [item["monthly_revenue"] for item in ordered]}],
        "currency",
    )
