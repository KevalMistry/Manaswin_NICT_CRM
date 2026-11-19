"""Reporting API.

The reports module is intentionally generic: every report returns the same
envelope (columns, rows, summary) so the frontend can render a table, export a
CSV and print it without any report-specific UI.

Access rules:

* The ``reports`` module must be granted to the role.
* Each report additionally requires the module that owns its data (fees,
  attendance, examinations, ...). The Super Admin always passes.
* Every non-Super-Admin user is limited to their branch. Faculty are further
  limited to the batches assigned to them.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    get_current_user,
    has_module_access,
    require_module,
)
from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.finance import BankAccount, Expense, FranchiseProfile, RoyaltyPayment
from app.models.placement import Company, JobOpening, PlacementApplication
from app.models.role import Role
from app.models.staff_attendance import StaffAttendance
from app.models.student import Student
from app.models.user import User
from app.core.config import GST_RATE_PERCENT
from app.services.analytics import month_windows


router = APIRouter(prefix="/api/reports", tags=["Reports"])
ReportsAccess = require_module("reports")

ROW_LIMIT = 5000


def _filter_rows_by_date(
    rows: list[dict],
    date_from: date | None,
    date_to: date | None,
) -> list[dict]:
    if date_from is None and date_to is None:
        return rows
    date_keys = (
        "admission_date", "payment_date", "attendance_date", "exam_date",
        "expense_date", "due_date", "follow_up_date", "converted_at",
        "start_date", "end_date", "issue_date", "review_month",
        "created_at", "date", "month",
    )
    filtered = []
    for row in rows:
        raw_value = next((row.get(key) for key in date_keys if row.get(key) not in (None, "—", "")), None)
        if raw_value is None:
            continue
        try:
            row_date = date.fromisoformat(str(raw_value)[:10])
        except ValueError:
            continue
        if date_from is not None and row_date < date_from:
            continue
        if date_to is not None and row_date > date_to:
            continue
        filtered.append(row)
    return filtered


def _filter_rows_by_course_and_batch(
    rows: list[dict], course_name: str | None, batch_name: str | None
) -> list[dict]:
    def matches(row: dict, key: str, expected: str | None) -> bool:
        if not expected:
            return True
        return str(row.get(key, "")).casefold() == expected.casefold()

    return [
        row for row in rows
        if matches(row, "course", course_name) and matches(row, "batch", batch_name)
    ]

STAFF_ROLES = ("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")


def _money(value) -> float:
    return round(float(Decimal(value or 0)), 2)


def _rate(part: int, total: int) -> float:
    return round((part / total) * 100, 2) if total else 0.0


def resolve_branch(current_user: User, requested: int | None) -> int | None:
    """Validate an optional ``branch_id`` filter against the user's scope."""
    if current_user.role.name == "Super Admin":
        return requested
    scope = branch_scope(current_user)
    if requested is not None and requested != scope:
        raise HTTPException(
            status_code=403,
            detail="You can run reports only for your assigned branch",
        )
    return scope


# ---------------------------------------------------------------------------
# Builders. Each returns {"columns": [...], "rows": [...], "summary": [...]}.
# ---------------------------------------------------------------------------


def build_admissions(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(Enrollment, Student, Batch, Course, Branch)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .join(Course, Batch.course_id == Course.id)
        .join(Branch, Batch.branch_id == Branch.id)
        .order_by(Enrollment.admission_date.desc(), Enrollment.id.desc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = [
        {
            "admission_date": enrollment.admission_date.isoformat(),
            "enrollment_code": enrollment.enrollment_code,
            "student_name": student.full_name,
            "student_code": student.student_code,
            "course": course.name,
            "batch": batch.name,
            "branch": branch.name,
            "status": enrollment.status.title(),
        }
        for enrollment, student, batch, course, branch in records
    ]
    active = sum(1 for row in rows if row["status"] == "Active")
    return {
        "columns": [
            {"key": "admission_date", "label": "Admission Date"},
            {"key": "enrollment_code", "label": "Enrollment"},
            {"key": "student_name", "label": "Student"},
            {"key": "student_code", "label": "Student Code"},
            {"key": "course", "label": "Course"},
            {"key": "batch", "label": "Batch"},
            {"key": "branch", "label": "Branch"},
            {"key": "status", "label": "Status"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Admissions", "value": len(rows)},
            {"label": "Active", "value": active},
            {"label": "Completed / Other", "value": len(rows) - active},
        ],
    }


def build_enquiry_conversion(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(Enquiry, Course)
        .outerjoin(Course, Enquiry.course_id == Course.id)
        .order_by(Enquiry.created_at.desc(), Enquiry.id.desc())
    )
    if branch_id is not None:
        query = query.where(Enquiry.branch_id == branch_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = [
        {
            "enquiry_code": enquiry.enquiry_code,
            "full_name": enquiry.full_name,
            "phone": enquiry.phone or "—",
            "course": course.name if course else "—",
            "source": enquiry.source.replace("_", " ").title(),
            "status": enquiry.status.replace("_", " ").title(),
            "follow_up_date": enquiry.follow_up_date.isoformat() if enquiry.follow_up_date else "—",
            "converted_at": enquiry.converted_at.strftime("%Y-%m-%d %H:%M") if enquiry.converted_at else "—",
        }
        for enquiry, course in records
    ]
    admitted = sum(1 for row in rows if row["status"] == "Admitted")
    lost = sum(1 for row in rows if row["status"] == "Lost")
    open_leads = len(rows) - admitted - lost
    return {
        "columns": [
            {"key": "enquiry_code", "label": "Enquiry"},
            {"key": "full_name", "label": "Name"},
            {"key": "phone", "label": "Phone"},
            {"key": "course", "label": "Course"},
            {"key": "source", "label": "Source"},
            {"key": "status", "label": "Status"},
            {"key": "follow_up_date", "label": "Follow-up"},
            {"key": "converted_at", "label": "Admitted On"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Total Enquiries", "value": len(rows)},
            {"label": "Admitted", "value": admitted},
            {"label": "Open Leads", "value": open_leads},
            {"label": "Conversion Rate", "value": f"{_rate(admitted, len(rows))}%"},
        ],
    }


def build_fee_collection(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(Payment, FeeInstallment, Enrollment, Student, Batch)
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = [
        {
            "receipt_number": payment.receipt_number,
            "payment_date": payment.payment_date.isoformat(),
            "student_name": student.full_name,
            "enrollment_code": enrollment.enrollment_code,
            "batch": batch.name,
            "installment": installment.installment_number,
            "amount": _money(payment.amount),
            "payment_method": payment.payment_method.replace("_", " ").title(),
            "reference": payment.reference or "—",
        }
        for payment, installment, enrollment, student, batch in records
    ]
    total = sum(row["amount"] for row in rows)
    return {
        "columns": [
            {"key": "receipt_number", "label": "Receipt"},
            {"key": "payment_date", "label": "Date"},
            {"key": "student_name", "label": "Student"},
            {"key": "enrollment_code", "label": "Enrollment"},
            {"key": "batch", "label": "Batch"},
            {"key": "installment", "label": "Instalment"},
            {"key": "amount", "label": "Amount"},
            {"key": "payment_method", "label": "Method"},
            {"key": "reference", "label": "Reference"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Total Collected", "value": f"₹{total:,.2f}"},
            {"label": "Payments", "value": len(rows)},
            {"label": "Average Payment", "value": f"₹{(total / len(rows)):,.2f}" if rows else "₹0.00"},
        ],
    }


def build_pending_fees(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    today = date.today()
    paid_subquery = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.installment_id == FeeInstallment.id)
        .scalar_subquery()
    )
    query = (
        select(FeeInstallment, Enrollment, Student, Batch, paid_subquery)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Enrollment.status != "cancelled")
        .order_by(FeeInstallment.due_date.asc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = []
    total_outstanding = 0.0
    overdue_total = 0.0
    for installment, enrollment, student, batch, paid in records:
        outstanding = _money(installment.amount) - _money(paid)
        if outstanding <= 0:
            continue
        days_overdue = (today - installment.due_date).days
        total_outstanding += outstanding
        if days_overdue > 0:
            overdue_total += outstanding
        rows.append(
            {
                "student_name": student.full_name,
                "enrollment_code": enrollment.enrollment_code,
                "batch": batch.name,
                "installment": installment.installment_number,
                "amount": _money(installment.amount),
                "paid": _money(paid),
                "outstanding": round(outstanding, 2),
                "due_date": installment.due_date.isoformat(),
                "days_overdue": max(days_overdue, 0),
                "status": "Overdue" if days_overdue > 0 else "Upcoming",
            }
        )

    return {
        "columns": [
            {"key": "student_name", "label": "Student"},
            {"key": "enrollment_code", "label": "Enrollment"},
            {"key": "batch", "label": "Batch"},
            {"key": "installment", "label": "Instalment"},
            {"key": "amount", "label": "Amount"},
            {"key": "paid", "label": "Paid"},
            {"key": "outstanding", "label": "Outstanding"},
            {"key": "due_date", "label": "Due Date"},
            {"key": "days_overdue", "label": "Days Overdue"},
            {"key": "status", "label": "Status"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Outstanding", "value": f"₹{total_outstanding:,.2f}"},
            {"label": "Overdue Amount", "value": f"₹{overdue_total:,.2f}"},
            {"label": "Open Instalments", "value": len(rows)},
        ],
    }


def build_student_attendance(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(
            Enrollment.enrollment_code,
            Student.full_name,
            Student.student_code,
            Batch.name,
            func.count(Attendance.id),
            func.coalesce(
                func.sum(case((Attendance.status.in_(("present", "late", "excused")), 1), else_=0)),
                0,
            ),
        )
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .outerjoin(Attendance, Attendance.enrollment_id == Enrollment.id)
        .where(Enrollment.status == "active")
        .group_by(
            Enrollment.id,
            Enrollment.enrollment_code,
            Student.full_name,
            Student.student_code,
            Batch.name,
        )
        .order_by(Student.full_name)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = []
    rate_total = 0.0
    low_attendance = 0
    for enrollment_code, student_name, student_code, batch_name, total, attended in records:
        total = int(total or 0)
        attended = int(attended or 0)
        rate = _rate(attended, total)
        rate_total += rate
        if total and rate < 75:
            low_attendance += 1
        rows.append(
            {
                "student_name": student_name,
                "student_code": student_code,
                "enrollment_code": enrollment_code,
                "batch": batch_name,
                "total_classes": total,
                "attended": attended,
                "attendance_rate": rate,
                "status": "At risk" if total and rate < 75 else "Healthy",
            }
        )

    return {
        "columns": [
            {"key": "student_name", "label": "Student"},
            {"key": "student_code", "label": "Student Code"},
            {"key": "enrollment_code", "label": "Enrollment"},
            {"key": "batch", "label": "Batch"},
            {"key": "total_classes", "label": "Classes"},
            {"key": "attended", "label": "Attended"},
            {"key": "attendance_rate", "label": "Attendance %"},
            {"key": "status", "label": "Status"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Students", "value": len(rows)},
            {
                "label": "Average Attendance",
                "value": f"{(rate_total / len(rows)):.2f}%" if rows else "0.00%",
            },
            {"label": "Below 75%", "value": low_attendance},
        ],
    }


def build_course_completion(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(
            Course.name,
            Batch.name,
            Batch.start_date,
            Batch.end_date,
            Batch.capacity,
            func.count(Enrollment.id),
            func.coalesce(
                func.sum(case((Enrollment.status == "completed", 1), else_=0)), 0
            ),
        )
        .join(Batch, Batch.course_id == Course.id)
        .join(Enrollment, Enrollment.batch_id == Batch.id)
        .group_by(
            Batch.id,
            Course.name,
            Batch.name,
            Batch.start_date,
            Batch.end_date,
            Batch.capacity,
        )
        .order_by(Batch.start_date.desc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = [
        {
            "course": course_name,
            "batch": batch_name,
            "start_date": start.isoformat() if start else "—",
            "end_date": end.isoformat() if end else "—",
            "capacity": capacity,
            "enrolled": int(enrolled or 0),
            "completed": int(completed or 0),
            "completion_rate": _rate(int(completed or 0), int(enrolled or 0)),
        }
        for course_name, batch_name, start, end, capacity, enrolled, completed in records
    ]
    overall = _rate(
        sum(row["completed"] for row in rows),
        sum(row["enrolled"] for row in rows),
    )
    return {
        "columns": [
            {"key": "course", "label": "Course"},
            {"key": "batch", "label": "Batch"},
            {"key": "start_date", "label": "Start"},
            {"key": "end_date", "label": "End"},
            {"key": "capacity", "label": "Capacity"},
            {"key": "enrolled", "label": "Enrolled"},
            {"key": "completed", "label": "Completed"},
            {"key": "completion_rate", "label": "Completion %"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Batches", "value": len(rows)},
            {"label": "Overall Completion", "value": f"{overall}%"},
        ],
    }


def build_exam_results(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(
            Examination.name,
            Examination.exam_date,
            Batch.name,
            Student.full_name,
            Enrollment.enrollment_code,
            ExamSubject.name,
            ExamMark.marks_obtained,
            ExamSubject.max_marks,
            ExamSubject.pass_marks,
            ExamMark.grade,
        )
        .join(Batch, Examination.batch_id == Batch.id)
        .join(ExamSubject, ExamSubject.examination_id == Examination.id)
        .join(ExamMark, ExamMark.exam_subject_id == ExamSubject.id)
        .join(Enrollment, ExamMark.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .where(Examination.is_published.is_(True))
        .order_by(Examination.exam_date.desc(), Student.full_name)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = []
    passed = 0
    percentage_total = 0.0
    for (
        exam_name,
        exam_date,
        batch_name,
        student_name,
        enrollment_code,
        subject_name,
        marks,
        max_marks,
        pass_marks,
        grade,
    ) in records:
        marks_value = _money(marks)
        max_value = _money(max_marks)
        is_pass = marks_value >= _money(pass_marks)
        if is_pass:
            passed += 1
        percent = _rate(marks_value, max_value) if max_value else 0.0
        percentage_total += percent
        rows.append(
            {
                "exam": exam_name,
                "exam_date": exam_date.isoformat() if exam_date else "—",
                "batch": batch_name,
                "student_name": student_name,
                "enrollment_code": enrollment_code,
                "subject": subject_name,
                "marks": marks_value,
                "max_marks": max_value,
                "percentage": percent,
                "grade": grade,
                "result": "Pass" if is_pass else "Fail",
            }
        )

    return {
        "columns": [
            {"key": "exam", "label": "Examination"},
            {"key": "exam_date", "label": "Date"},
            {"key": "batch", "label": "Batch"},
            {"key": "student_name", "label": "Student"},
            {"key": "enrollment_code", "label": "Enrollment"},
            {"key": "subject", "label": "Subject"},
            {"key": "marks", "label": "Marks"},
            {"key": "max_marks", "label": "Max"},
            {"key": "percentage", "label": "%"},
            {"key": "grade", "label": "Grade"},
            {"key": "result", "label": "Result"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Result Rows", "value": len(rows)},
            {"label": "Pass Rate", "value": f"{_rate(passed, len(rows))}%"},
            {
                "label": "Average Score",
                "value": f"{(percentage_total / len(rows)):.2f}%" if rows else "0.00%",
            },
        ],
    }


def build_revenue(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    windows = month_windows(12)
    rows = []
    for start, end, label in windows:
        query = (
            select(
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
            .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
            .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Payment.payment_date >= start, Payment.payment_date <= end)
        )
        if branch_id is not None:
            query = query.where(Batch.branch_id == branch_id)
        if faculty_id is not None:
            query = query.where(Batch.faculty_id == faculty_id)
        amount, payments = db.execute(query).one()
        rows.append(
            {
                "month": label,
                "collected": _money(amount),
                "payments": int(payments or 0),
            }
        )
    total = sum(row["collected"] for row in rows)
    return {
        "columns": [
            {"key": "month", "label": "Month"},
            {"key": "collected", "label": "Collected"},
            {"key": "payments", "label": "Payments"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Last 12 Months", "value": f"₹{total:,.2f}"},
            {"label": "Average / Month", "value": f"₹{(total / len(rows)):,.2f}" if rows else "₹0.00"},
        ],
    }


def build_payment_methods(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(
            Payment.payment_method,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .group_by(Payment.payment_method)
        .order_by(func.sum(Payment.amount).desc())
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query).all()

    total = sum(_money(record[2]) for record in records)
    rows = [
        {
            "method": method.replace("_", " ").title(),
            "payments": int(count or 0),
            "amount": _money(amount),
            "share": _rate(round(_money(amount)), round(total)) if total else 0.0,
        }
        for method, count, amount in records
    ]
    return {
        "columns": [
            {"key": "method", "label": "Method"},
            {"key": "payments", "label": "Payments"},
            {"key": "amount", "label": "Collected"},
            {"key": "share", "label": "Share %"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Collected", "value": f"₹{total:,.2f}"},
            {"label": "Methods Used", "value": len(rows)},
            {"label": "Top Method", "value": rows[0]["method"] if rows else "—"},
        ],
    }


def build_batch_fill(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(
            Batch.name,
            Batch.code,
            Course.name,
            User.full_name,
            Branch.name,
            Batch.capacity,
            func.count(Enrollment.id),
        )
        .join(Course, Batch.course_id == Course.id)
        .join(Branch, Batch.branch_id == Branch.id)
        .outerjoin(User, Batch.faculty_id == User.id)
        .outerjoin(
            Enrollment,
            and_(Enrollment.batch_id == Batch.id, Enrollment.status == "active"),
        )
        .where(Batch.is_active.is_(True))
        .group_by(
            Batch.id,
            Batch.name,
            Batch.code,
            Course.name,
            User.full_name,
            Branch.name,
            Batch.capacity,
        )
        .order_by(Batch.name)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if faculty_id is not None:
        query = query.where(Batch.faculty_id == faculty_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = [
        {
            "batch": batch_name,
            "code": code,
            "course": course_name,
            "faculty": faculty_name or "Unassigned",
            "branch": branch_name,
            "capacity": int(capacity or 0),
            "enrolled": int(enrolled or 0),
            "available": max(int(capacity or 0) - int(enrolled or 0), 0),
            "fill_rate": _rate(int(enrolled or 0), int(capacity or 0)),
        }
        for batch_name, code, course_name, faculty_name, branch_name, capacity, enrolled in records
    ]
    return {
        "columns": [
            {"key": "batch", "label": "Batch"},
            {"key": "code", "label": "Code"},
            {"key": "course", "label": "Course"},
            {"key": "faculty", "label": "Faculty"},
            {"key": "branch", "label": "Branch"},
            {"key": "capacity", "label": "Capacity"},
            {"key": "enrolled", "label": "Enrolled"},
            {"key": "available", "label": "Seats Left"},
            {"key": "fill_rate", "label": "Fill %"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Active Batches", "value": len(rows)},
            {
                "label": "Overall Fill",
                "value": f"{_rate(sum(r['enrolled'] for r in rows), sum(r['capacity'] for r in rows))}%",
            },
        ],
    }


def build_faculty_attendance(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    windows = month_windows(6)
    columns = [
        {"key": "month", "label": "Month"},
        {"key": "staff", "label": "Faculty / Staff"},
        {"key": "role", "label": "Role"},
        {"key": "branch", "label": "Branch"},
        {"key": "present", "label": "Present"},
        {"key": "absent", "label": "Absent"},
        {"key": "late", "label": "Late"},
        {"key": "leave", "label": "Leave"},
        {"key": "half_day", "label": "Half Day"},
        {"key": "recorded_days", "label": "Recorded Days"},
        {"key": "attendance_rate", "label": "Attendance %"},
    ]
    if not windows:
        return {"columns": columns, "rows": [], "summary": []}

    start = windows[0][0]
    end = windows[-1][1]
    query = (
        select(StaffAttendance, User, Role, Branch)
        .join(User, StaffAttendance.user_id == User.id)
        .join(Role, User.role_id == Role.id)
        .outerjoin(Branch, User.branch_id == Branch.id)
        .where(
            StaffAttendance.attendance_date >= start,
            StaffAttendance.attendance_date <= end,
        )
    )
    if branch_id is not None:
        query = query.where(User.branch_id == branch_id)
    records = db.execute(query).all()

    def window_for(value: date) -> str | None:
        for window_start, window_end, label in windows:
            if window_start <= value <= window_end:
                return label
        return None

    buckets: dict[tuple[str, int], dict] = {}
    for attendance, user, role, branch in records:
        label = window_for(attendance.attendance_date)
        if label is None:
            continue
        key = (label, user.id)
        row = buckets.get(key)
        if row is None:
            row = {
                "month": label,
                "staff": user.full_name,
                "role": role.name,
                "branch": branch.name if branch else "—",
                "present": 0,
                "absent": 0,
                "late": 0,
                "leave": 0,
                "half_day": 0,
                "recorded_days": 0,
                "attendance_rate": 0.0,
            }
            buckets[key] = row
        if attendance.status in row:
            row[attendance.status] += 1
        row["recorded_days"] += 1

    rows = []
    for row in buckets.values():
        recorded = row["recorded_days"]
        attended = row["present"] + row["late"] + (row["half_day"] * 0.5)
        row["attendance_rate"] = _rate(round(attended), recorded) if recorded else 0.0
        rows.append(row)

    month_order = {label: index for index, (_start, _end, label) in enumerate(windows)}
    rows.sort(key=lambda row: (-month_order.get(row["month"], 99), row["staff"]))

    staff_ids = {user.id for _attendance, user, _role, _branch in records}
    total_recorded = sum(row["recorded_days"] for row in rows)
    total_attended = sum(
        row["present"] + row["late"] + (row["half_day"] * 0.5) for row in rows
    )
    return {
        "columns": columns,
        "rows": rows,
        "summary": [
            {"label": "Staff Tracked", "value": len(staff_ids)},
            {"label": "Days Recorded", "value": total_recorded},
            {
                "label": "Average Attendance",
                "value": f"{_rate(round(total_attended), total_recorded)}%"
                if total_recorded
                else "0.00%",
            },
        ],
    }


def build_placement(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(PlacementApplication, Student, JobOpening, Company, Branch)
        .join(Student, PlacementApplication.student_id == Student.id)
        .join(JobOpening, PlacementApplication.job_opening_id == JobOpening.id)
        .join(Company, JobOpening.company_id == Company.id)
        .join(Branch, Student.branch_id == Branch.id)
        .order_by(PlacementApplication.applied_at.desc(), PlacementApplication.id.desc())
    )
    if branch_id is not None:
        query = query.where(Student.branch_id == branch_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    student_ids = {student.id for _, student, _, _, _ in records}
    course_map: dict[int, list[str]] = {}
    if student_ids:
        course_rows = db.execute(
            select(Enrollment.student_id, Course.name)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .join(Course, Batch.course_id == Course.id)
            .where(Enrollment.student_id.in_(student_ids))
            .order_by(Course.name)
        ).all()
        for student_id, course_name in course_rows:
            names = course_map.setdefault(student_id, [])
            if course_name not in names:
                names.append(course_name)

    openings = {row[2].id: row[2] for row in records}
    eligibility: dict[int, str] = {}
    if openings:
        opening_ids = list(openings)
        for opening_id in opening_ids:
            opening = db.get(JobOpening, opening_id)
            if opening is None:
                continue
            eligibility[opening_id] = (
                ", ".join(course.name for course in opening.courses) or "All courses"
            )

    rows = []
    for application, student, opening, company, branch in records:
        rows.append(
            {
                "applied_at": application.applied_at.date().isoformat(),
                "student_name": student.full_name,
                "student_code": student.student_code,
                "branch": branch.name,
                "company": company.name,
                "role": opening.title,
                "course": ", ".join(course_map.get(student.id, [])) or "—",
                "eligibility": eligibility.get(opening.id, "All courses"),
                "status": application.status.replace("_", " ").title(),
                "interview": (
                    application.interview_date.strftime("%Y-%m-%d %H:%M")
                    if application.interview_date
                    else "—"
                ),
                "offer_salary": _money(application.offer_salary)
                if application.offer_salary is not None
                else "—",
                "joining_date": application.joining_date.isoformat()
                if application.joining_date
                else "—",
                "source": application.source.title(),
            }
        )

    in_process = sum(
        1
        for app, _, _, _, _ in records
        if app.status not in {"joined", "rejected", "withdrawn"}
    )
    offers = sum(
        1 for app, _, _, _, _ in records if app.status in {"offer_released", "joined"}
    )
    joined = sum(1 for app, _, _, _, _ in records if app.status == "joined")
    rejected = sum(1 for app, _, _, _, _ in records if app.status == "rejected")
    return {
        "columns": [
            {"key": "applied_at", "label": "Applied"},
            {"key": "student_name", "label": "Student"},
            {"key": "student_code", "label": "Student Code"},
            {"key": "branch", "label": "Branch"},
            {"key": "course", "label": "Student Course"},
            {"key": "company", "label": "Company"},
            {"key": "role", "label": "Role"},
            {"key": "eligibility", "label": "Eligibility"},
            {"key": "status", "label": "Status"},
            {"key": "interview", "label": "Interview"},
            {"key": "offer_salary", "label": "Offer Salary"},
            {"key": "joining_date", "label": "Joining Date"},
            {"key": "source", "label": "Source"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Applications", "value": len(rows)},
            {"label": "In Process", "value": in_process},
            {"label": "Offers", "value": offers},
            {"label": "Joined", "value": joined},
            {"label": "Rejected", "value": rejected},
            {
                "label": "Conversion Rate",
                "value": f"{_rate(joined, len(rows))}%",
            },
        ],
    }


def _gst_of(amount: float) -> float:
    """Return the inclusive GST portion of an amount at the configured rate."""
    if not amount or GST_RATE_PERCENT <= 0:
        return 0.0
    return round(amount * GST_RATE_PERCENT / (100 + GST_RATE_PERCENT), 2)


def _branch_revenue(db: Session, branch_id: int | None) -> float:
    query = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    return _money(db.scalar(query))


def _branch_outstanding(db: Session, branch_id: int | None) -> float:
    paid = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.installment_id == FeeInstallment.id)
        .scalar_subquery()
    )
    query = (
        select(func.coalesce(func.sum(FeeInstallment.amount - paid), 0))
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    return _money(db.scalar(query))


def _expense_rows(db: Session, branch_id: int | None):
    query = (
        select(Expense, Branch)
        .join(Branch, Expense.branch_id == Branch.id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
    )
    if branch_id is not None:
        query = query.where(Expense.branch_id == branch_id)
    return db.execute(query.limit(ROW_LIMIT)).all()


def build_expense(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    records = _expense_rows(db, branch_id)
    rows = [
        {
            "expense_date": expense.expense_date.isoformat(),
            "branch": branch.name,
            "category": expense.category,
            "description": expense.description,
            "vendor": expense.vendor or "—",
            "amount": _money(expense.amount),
            "gst_amount": _money(expense.gst_amount),
            "payment_method": expense.payment_method,
            "reference": expense.reference or "—",
        }
        for expense, branch in records
    ]
    total = sum(row["amount"] for row in rows)
    total_gst = sum(row["gst_amount"] for row in rows)
    by_category: dict[str, float] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + row["amount"]
    top = max(by_category.items(), key=lambda item: item[1]) if by_category else ("—", 0)
    return {
        "columns": [
            {"key": "expense_date", "label": "Date"},
            {"key": "branch", "label": "Branch"},
            {"key": "category", "label": "Category"},
            {"key": "description", "label": "Description"},
            {"key": "vendor", "label": "Vendor"},
            {"key": "amount", "label": "Amount"},
            {"key": "gst_amount", "label": "GST"},
            {"key": "payment_method", "label": "Method"},
            {"key": "reference", "label": "Reference"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Total Expenses", "value": f"₹{total:,.2f}"},
            {"label": "Entries", "value": len(rows)},
            {"label": "GST Paid", "value": f"₹{total_gst:,.2f}"},
            {"label": "Top Category", "value": f"{top[0]} (₹{top[1]:,.2f})"},
        ],
    }


def build_gst(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    output_gst = 0.0
    input_gst = 0.0
    rows = []
    for start, end, label in month_windows(12):
        fee_query = (
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
            .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
            .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Payment.payment_date >= start, Payment.payment_date <= end)
        )
        expense_query = select(
            func.coalesce(func.sum(Expense.amount), 0),
            func.coalesce(func.sum(Expense.gst_amount), 0),
        ).where(Expense.expense_date >= start, Expense.expense_date <= end)
        if branch_id is not None:
            fee_query = fee_query.where(Batch.branch_id == branch_id)
            expense_query = expense_query.where(Expense.branch_id == branch_id)
        fees = _money(db.scalar(fee_query))
        expense_total, expense_gst = db.execute(expense_query).one()
        output = _gst_of(fees)
        input_tax = _money(expense_gst)
        output_gst += output
        input_gst += input_tax
        rows.append(
            {
                "month": label,
                "taxable_income": round(fees - output, 2),
                "output_gst": output,
                "expense_value": round(_money(expense_total) - input_tax, 2),
                "input_gst": input_tax,
                "net_payable": round(output - input_tax, 2),
            }
        )
    return {
        "columns": [
            {"key": "month", "label": "Month"},
            {"key": "taxable_income", "label": "Taxable Income"},
            {"key": "output_gst", "label": "Output GST"},
            {"key": "expense_value", "label": "Expense Value"},
            {"key": "input_gst", "label": "Input GST"},
            {"key": "net_payable", "label": "Net Payable"},
        ],
        "rows": rows,
        "summary": [
            {"label": "GST Rate", "value": f"{GST_RATE_PERCENT:.2f}% (inclusive)"},
            {"label": "Output GST", "value": f"₹{output_gst:,.2f}"},
            {"label": "Input GST", "value": f"₹{input_gst:,.2f}"},
            {"label": "Net Payable", "value": f"₹{max(output_gst - input_gst, 0):,.2f}"},
        ],
    }


def build_profit_loss(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    income = _branch_revenue(db, branch_id)
    expense_query = select(Expense.category, func.sum(Expense.amount)).group_by(
        Expense.category
    )
    if branch_id is not None:
        expense_query = expense_query.where(Expense.branch_id == branch_id)
    category_totals = {
        category: _money(total)
        for category, total in db.execute(expense_query).all()
    }
    total_expenses = sum(category_totals.values())
    rows = [
        {
            "line_item": "Income",
            "category": "Fee Collection",
            "amount": income,
            "share": 100.0,
        }
    ]
    for category, amount in sorted(category_totals.items(), key=lambda item: -item[1]):
        rows.append(
            {
                "line_item": "Expense",
                "category": category,
                "amount": amount,
                "share": _rate(amount, income) if income else 0.0,
            }
        )
    net = income - total_expenses
    return {
        "columns": [
            {"key": "line_item", "label": "Line"},
            {"key": "category", "label": "Category"},
            {"key": "amount", "label": "Amount"},
            {"key": "share", "label": "% of Income"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Total Income", "value": f"₹{income:,.2f}"},
            {"label": "Total Expenses", "value": f"₹{total_expenses:,.2f}"},
            {
                "label": "Net Profit",
                "value": f"₹{net:,.2f}",
            },
            {"label": "Profit Margin", "value": f"{_rate(net, income) if income else 0.0}%"},
        ],
    }


def build_balance_sheet(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    bank_query = select(func.coalesce(func.sum(BankAccount.opening_balance), 0)).where(
        BankAccount.is_active.is_(True)
    )
    if branch_id is not None:
        bank_query = bank_query.where(BankAccount.branch_id == branch_id)
    opening = _money(db.scalar(bank_query))

    expense_query = select(func.coalesce(func.sum(Expense.amount), 0))
    if branch_id is not None:
        expense_query = expense_query.where(Expense.branch_id == branch_id)
    expenses = _money(db.scalar(expense_query))

    collected = _branch_revenue(db, branch_id)
    outstanding = _branch_outstanding(db, branch_id)
    cash = round(opening + collected - expenses, 2)

    profile_query = select(FranchiseProfile).where(
        FranchiseProfile.status == "active"
    )
    if branch_id is not None:
        profile_query = profile_query.where(FranchiseProfile.branch_id == branch_id)
    royalty_due = 0.0
    for profile in db.scalars(profile_query).all():
        revenue = _branch_revenue(db, profile.branch_id)
        expected = revenue * float(profile.royalty_percent) / 100
        paid = _money(
            db.scalar(
                select(func.coalesce(func.sum(RoyaltyPayment.amount), 0)).where(
                    RoyaltyPayment.franchise_id == profile.id
                )
            )
        )
        royalty_due += expected - paid

    rows = [
        {"group": "Asset", "item": "Cash & Bank", "amount": cash},
        {"group": "Asset", "item": "Fees Receivable", "amount": outstanding},
        {"group": "Liability", "item": "Royalty Payable", "amount": round(max(royalty_due, 0), 2)},
        {"group": "Equity", "item": "Retained Earnings", "amount": round(cash + outstanding - max(royalty_due, 0), 2)},
    ]
    total_assets = cash + outstanding
    total_liabilities = round(max(royalty_due, 0), 2)
    return {
        "columns": [
            {"key": "group", "label": "Group"},
            {"key": "item", "label": "Item"},
            {"key": "amount", "label": "Amount"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Total Assets", "value": f"₹{total_assets:,.2f}"},
            {"label": "Total Liabilities", "value": f"₹{total_liabilities:,.2f}"},
            {"label": "Net Worth", "value": f"₹{total_assets - total_liabilities:,.2f}"},
        ],
    }


def build_franchise(db: Session, branch_id: int | None, faculty_id: int | None) -> dict:
    query = (
        select(FranchiseProfile, Branch)
        .join(Branch, FranchiseProfile.branch_id == Branch.id)
        .order_by(Branch.name)
    )
    if branch_id is not None:
        query = query.where(FranchiseProfile.branch_id == branch_id)
    records = db.execute(query.limit(ROW_LIMIT)).all()

    rows = []
    total_revenue = 0.0
    total_royalty = 0.0
    total_paid = 0.0
    for profile, branch in records:
        revenue = _branch_revenue(db, profile.branch_id)
        expected = round(revenue * float(profile.royalty_percent) / 100, 2)
        paid = _money(
            db.scalar(
                select(func.coalesce(func.sum(RoyaltyPayment.amount), 0)).where(
                    RoyaltyPayment.franchise_id == profile.id
                )
            )
        )
        students = int(
            db.scalar(
                select(func.count(Student.id)).where(
                    Student.branch_id == profile.branch_id, Student.is_active.is_(True)
                )
            )
            or 0
        )
        total_revenue += revenue
        total_royalty += expected
        total_paid += paid
        rows.append(
            {
                "branch": branch.name,
                "branch_code": branch.code,
                "owner": profile.owner_name,
                "status": profile.status.title(),
                "agreement_start": profile.agreement_start.isoformat(),
                "royalty_percent": float(profile.royalty_percent),
                "students": students,
                "revenue": revenue,
                "royalty_expected": expected,
                "royalty_paid": paid,
                "royalty_due": round(expected - paid, 2),
            }
        )
    return {
        "columns": [
            {"key": "branch", "label": "Branch"},
            {"key": "branch_code", "label": "Code"},
            {"key": "owner", "label": "Franchise Owner"},
            {"key": "status", "label": "Status"},
            {"key": "agreement_start", "label": "Agreement Start"},
            {"key": "royalty_percent", "label": "Royalty %"},
            {"key": "students", "label": "Students"},
            {"key": "revenue", "label": "Revenue"},
            {"key": "royalty_expected", "label": "Royalty Expected"},
            {"key": "royalty_paid", "label": "Royalty Paid"},
            {"key": "royalty_due", "label": "Royalty Due"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Franchises", "value": len(rows)},
            {"label": "Total Revenue", "value": f"₹{total_revenue:,.2f}"},
            {"label": "Royalty Expected", "value": f"₹{total_royalty:,.2f}"},
            {"label": "Royalty Paid", "value": f"₹{total_paid:,.2f}"},
            {"label": "Royalty Due", "value": f"₹{max(total_royalty - total_paid, 0):,.2f}"},
        ],
    }


REPORT_DEFINITIONS: dict[str, dict] = {
    "admissions": {
        "title": "Admission Report",
        "description": "Every enrollment with student, course, batch and branch.",
        "module": "enrollments",
        "roles": ("Super Admin", "Branch Admin", "Staff", "Counsellor"),
        "builder": build_admissions,
    },
    "enquiry-conversion": {
        "title": "Inquiry Conversion Report",
        "description": "Lead sources, pipeline status and conversion rate.",
        "module": "enquiries",
        "roles": ("Super Admin", "Branch Admin", "Staff", "Counsellor"),
        "builder": build_enquiry_conversion,
    },
    "fee-collection": {
        "title": "Fee Collection Report",
        "description": "All recorded payments with receipt, method and reference.",
        "module": "fees",
        "roles": ("Super Admin", "Branch Admin", "Staff"),
        "builder": build_fee_collection,
    },
    "pending-fees": {
        "title": "Pending Fees Report",
        "description": "Outstanding installments with aging and days overdue.",
        "module": "fees",
        "roles": ("Super Admin", "Branch Admin", "Staff"),
        "builder": build_pending_fees,
    },
    "student-attendance": {
        "title": "Student Attendance Report",
        "description": "Per-student attendance percentage and at-risk list.",
        "module": "attendance",
        "roles": ("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor"),
        "builder": build_student_attendance,
    },
    "faculty-attendance": {
        "title": "Faculty Attendance Report",
        "description": "Monthly attendance summary for faculty and staff.",
        "module": "attendance",
        "roles": ("Super Admin", "Branch Admin"),
        "builder": build_faculty_attendance,
    },
    "course-completion": {
        "title": "Course Completion Report",
        "description": "Batch completion progress against enrolled students.",
        "module": "courses",
        "roles": ("Super Admin", "Branch Admin", "Faculty", "Staff"),
        "builder": build_course_completion,
    },
    "exam-results": {
        "title": "Exam Results Report",
        "description": "Published subject-wise marks, grades and pass rate.",
        "module": "examinations",
        "roles": ("Super Admin", "Branch Admin", "Faculty", "Staff"),
        "builder": build_exam_results,
    },
    "revenue": {
        "title": "Revenue Report",
        "description": "Monthly collection trend for the last twelve months.",
        "module": "fees",
        "roles": ("Super Admin", "Branch Admin"),
        "builder": build_revenue,
    },
    "payment-methods": {
        "title": "Payment Methods Report",
        "description": "Collection split by cash, UPI, card, cheque and transfer.",
        "module": "fees",
        "roles": ("Super Admin", "Branch Admin", "Staff"),
        "builder": build_payment_methods,
    },
    "batch-fill": {
        "title": "Batch Fill Report",
        "description": "Seat utilisation for every active batch.",
        "module": "courses",
        "roles": ("Super Admin", "Branch Admin", "Staff"),
        "builder": build_batch_fill,
    },
    "placement": {
        "title": "Placement Report",
        "description": "Application pipeline, interviews, offers and joining by branch.",
        "module": "placement",
        "roles": ("Super Admin", "Branch Admin", "Staff", "Counsellor"),
        "builder": build_placement,
    },
    "expense": {
        "title": "Expense Report",
        "description": "Every recorded expense with category, vendor and GST.",
        "module": "finance",
        "roles": ("Super Admin", "Branch Admin", "Staff"),
        "builder": build_expense,
    },
    "gst": {
        "title": "GST Report",
        "description": "Output and input GST with monthly net payable.",
        "module": "finance",
        "roles": ("Super Admin", "Branch Admin"),
        "builder": build_gst,
    },
    "profit-loss": {
        "title": "Profit & Loss Report",
        "description": "Fee income against expenses by category with net profit.",
        "module": "finance",
        "roles": ("Super Admin", "Branch Admin"),
        "builder": build_profit_loss,
    },
    "balance-sheet": {
        "title": "Balance Sheet Report",
        "description": "Cash, receivables, royalty payable and net worth.",
        "module": "finance",
        "roles": ("Super Admin", "Branch Admin"),
        "builder": build_balance_sheet,
    },
    "franchise": {
        "title": "Franchise Report",
        "description": "Franchise revenue, royalty expected, paid and due.",
        "module": "franchises",
        "roles": ("Super Admin",),
        "builder": build_franchise,
    },
}


def _role_of(current_user: User) -> str:
    return current_user.role.name if current_user.role else ""


def _ensure_report_access(db: Session, current_user: User, definition: dict) -> None:
    role = _role_of(current_user)
    if role not in definition["roles"]:
        raise HTTPException(
            status_code=403,
            detail="Your role cannot run this report",
        )
    if not has_module_access(current_user, db, definition["module"]):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to the data behind this report",
        )


@router.get("/catalog", dependencies=[Depends(ReportsAccess)])
def report_catalog(
    db: DatabaseSession,
    current_user: User = Depends(get_current_user),
) -> dict:
    role = _role_of(current_user)
    reports = []
    for key, definition in REPORT_DEFINITIONS.items():
        if role not in definition["roles"]:
            continue
        if not has_module_access(current_user, db, definition["module"]):
            continue
        reports.append(
            {
                "key": key,
                "title": definition["title"],
                "description": definition["description"],
            }
        )
    return {"reports": reports}


@router.get("/{report_key}", dependencies=[Depends(ReportsAccess)])
def run_report(
    report_key: str,
    db: DatabaseSession,
    branch_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    course_name: str | None = Query(default=None, max_length=150),
    batch_name: str | None = Query(default=None, max_length=150),
    current_user: User = Depends(get_current_user),
) -> dict:
    definition = REPORT_DEFINITIONS.get(report_key)
    if definition is None:
        raise HTTPException(status_code=404, detail="Report not found")

    _ensure_report_access(db, current_user, definition)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=400, detail="From date cannot be after To date")
    scoped_branch = resolve_branch(current_user, branch_id)
    faculty_id = current_user.id if _role_of(current_user) == "Faculty" else None

    payload = definition["builder"](db, scoped_branch, faculty_id)
    payload["rows"] = _filter_rows_by_course_and_batch(payload["rows"], course_name, batch_name)
    payload["rows"] = _filter_rows_by_date(payload["rows"], date_from, date_to)
    if date_from is not None or date_to is not None or course_name or batch_name:
        payload["summary"] = [
            {"label": "Filtered records", "value": len(payload["rows"])}
        ]
    scope_label = "All Branches"
    if scoped_branch is not None:
        branch = db.get(Branch, scoped_branch)
        scope_label = branch.name if branch else f"Branch {scoped_branch}"
    if faculty_id is not None:
        scope_label = f"{current_user.full_name}'s Batches"

    return {
        "key": report_key,
        "title": definition["title"],
        "description": definition["description"],
        "scope": scope_label,
        "generated_at": date.today().isoformat(),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "course_name": course_name,
        "batch_name": batch_name,
        "columns": payload["columns"],
        "rows": payload["rows"],
        "summary": payload["summary"],
    }
