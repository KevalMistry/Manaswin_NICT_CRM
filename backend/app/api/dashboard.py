from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    require_roles,
)
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.responsibility import Responsibility
from app.models.role import Role
from app.models.staff_attendance import StaffAttendance
from app.models.student import Student
from app.models.user import User
from app.services.analytics import (
    attendance_trend,
    batch_students,
    branch_revenue,
    course_popularity,
    enquiry_funnel,
    enquiry_sources,
    exam_grade_distribution,
    fee_aging,
    monthly_admissions,
    monthly_revenue,
    payment_method_split,
)


router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
# The dashboard exposes branch-wide financial and operational metrics, so it is
# limited to staff roles. Students and parents have their own portals.
DashboardUser = require_roles(
    "Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor"
)


def staff_attendance_snapshot(db, user_id: int) -> dict:
    """Return the current month's attendance snapshot for one staff member."""
    today = date.today()
    start = today.replace(day=1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    counts = dict(
        db.execute(
            select(StaffAttendance.status, func.count(StaffAttendance.id))
            .where(
                StaffAttendance.user_id == user_id,
                StaffAttendance.attendance_date >= start,
                StaffAttendance.attendance_date <= end,
            )
            .group_by(StaffAttendance.status)
        ).all()
    )
    present = int(counts.get("present", 0))
    late = int(counts.get("late", 0))
    half_day = int(counts.get("half_day", 0))
    absent = int(counts.get("absent", 0))
    leave = int(counts.get("leave", 0))
    recorded = present + late + half_day + absent + leave
    attended = present + late + (half_day * 0.5)
    return {
        "present": present,
        "absent": absent,
        "late": late,
        "leave": leave,
        "half_day": half_day,
        "recorded_days": recorded,
        "attendance_rate": round((attended / recorded) * 100, 2) if recorded else 0.0,
    }


def branch_staff_attendance_snapshot(db, branch_id: int) -> dict:
    today = date.today()
    staff_ids = select(User.id).join(Role).where(
        User.branch_id == branch_id,
        User.is_active.is_(True),
        Role.name.in_(("Faculty", "Staff", "Counsellor", "Branch Admin")),
    )
    counts = dict(
        db.execute(
            select(StaffAttendance.status, func.count(StaffAttendance.id))
            .where(
                StaffAttendance.user_id.in_(staff_ids),
                StaffAttendance.attendance_date == today,
            )
            .group_by(StaffAttendance.status)
        ).all()
    )
    present = int(counts.get("present", 0)) + int(counts.get("late", 0))
    on_leave = int(counts.get("leave", 0))
    recorded = sum(int(value) for value in counts.values())
    return {
        "present_today": present,
        "on_leave_today": on_leave,
        "recorded_today": recorded,
    }


def get_monthly_collection(db: DatabaseSession, branch_id: int | None = None) -> float:
    today = date.today()
    query = (
        select(func.coalesce(func.sum(Payment.amount), Decimal("0")))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .where(Payment.payment_date >= today.replace(day=1))
    )
    if branch_id is not None:
        query = (
            query.join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Batch.branch_id == branch_id)
        )
    return float(db.scalar(query) or 0.0)


def get_branch_attendance_rate(db: DatabaseSession, branch_id: int | None = None) -> float:
    query = (
        select(
            func.count(Attendance.id),
            func.sum(case((Attendance.status.in_(("present", "late", "excused")), 1), else_=0)),
        )
        .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    total, attended = db.execute(query).one()
    total = int(total or 0)
    attended = int(attended or 0)
    return round((attended / total) * 100, 2) if total else 0.0


def build_super_admin_dashboard(db: DatabaseSession, current_user: User) -> dict:
    today = date.today()
    branches = db.scalars(select(Branch).order_by(Branch.name)).all()
    branch_summaries = []

    for b in branches:
        student_count = db.scalar(
            select(func.count(Student.id)).where(Student.branch_id == b.id, Student.is_active.is_(True))
        ) or 0
        batch_count = db.scalar(
            select(func.count(Batch.id)).where(Batch.branch_id == b.id, Batch.is_active.is_(True))
        ) or 0
        monthly_rev = get_monthly_collection(db, b.id)
        att_rate = get_branch_attendance_rate(db, b.id)
        branch_admin = db.scalar(
            select(User)
            .join(Role)
            .where(User.branch_id == b.id, Role.name == "Branch Admin", User.is_active.is_(True))
        )

        branch_summaries.append({
            "id": b.id,
            "name": b.name,
            "code": b.code,
            "address": b.address,
            "phone": b.phone,
            "email": b.email,
            "is_active": b.is_active,
            "admin_name": branch_admin.full_name if branch_admin else "Not Assigned",
            "students_count": int(student_count),
            "batches_count": int(batch_count),
            "monthly_revenue": monthly_rev,
            "attendance_rate": att_rate,
        })

    total_revenue = float(db.scalar(select(func.coalesce(func.sum(Payment.amount), Decimal("0")))) or 0.0)
    total_faculty = db.scalar(select(func.count(User.id)).join(Role).where(Role.name == "Faculty", User.is_active.is_(True))) or 0
    total_staff = db.scalar(select(func.count(User.id)).join(Role).where(Role.name.in_(["Branch Admin", "Staff", "Counsellor"]), User.is_active.is_(True))) or 0

    recent_logs = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)
    ).all()
    log_items = []
    for log in recent_logs:
        actor = db.get(User, log.actor_id) if log.actor_id else None
        log_items.append({
            "id": log.id,
            "actor_name": actor.full_name if actor else "System",
            "action": log.action.replace("_", " ").title(),
            "resource_type": log.resource_type.title(),
            "resource_id": log.resource_id,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        })

    aging = fee_aging(db, None)

    return {
        "dashboard_type": "super_admin",
        "total_branches": len(branches),
        "active_branches": len([b for b in branches if b.is_active]),
        "total_students": sum(b["students_count"] for b in branch_summaries),
        "total_faculty": int(total_faculty),
        "total_staff": int(total_staff),
        "monthly_revenue": sum(b["monthly_revenue"] for b in branch_summaries),
        "total_revenue": total_revenue,
        "total_outstanding": sum(aging["series"][0]["data"]),
        "overall_attendance_rate": get_branch_attendance_rate(db),
        "branches": branch_summaries,
        "recent_activities": log_items,
        "charts": {
            "revenue_trend": monthly_revenue(db, 6, None),
            "admissions_trend": monthly_admissions(db, 6, None),
            "branch_revenue": branch_revenue(db, branch_summaries),
            "course_popularity": course_popularity(db, None),
            "fee_aging": aging,
        },
    }


def build_branch_admin_dashboard(db: DatabaseSession, current_user: User) -> dict:
    branch_id = current_user.branch_id
    branch = db.get(Branch, branch_id) if branch_id else None

    batches_query = (
        select(Batch)
        .options(joinedload(Batch.course), joinedload(Batch.faculty))
        .where(Batch.branch_id == branch_id, Batch.is_active.is_(True))
        .order_by(Batch.start_date.desc())
    )
    batches = db.scalars(batches_query).all()
    batch_items = []
    for b in batches:
        enrolled = db.scalar(
            select(func.count(Enrollment.id)).where(Enrollment.batch_id == b.id, Enrollment.status == "active")
        ) or 0
        batch_items.append({
            "id": b.id,
            "name": b.name,
            "code": b.code,
            "course_name": b.course.name if b.course else "Unknown",
            "faculty_name": b.faculty.full_name if b.faculty else "Unassigned",
            "enrolled_count": int(enrolled),
            "capacity": b.capacity,
            "start_date": b.start_date.isoformat() if b.start_date else "",
            "end_date": b.end_date.isoformat() if b.end_date else None,
        })

    # Outstanding fees calculation in this branch
    total_due = db.scalar(
        select(func.coalesce(func.sum(FeePlan.total_amount - FeePlan.discount_amount - FeePlan.scholarship_amount), Decimal("0")))
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.branch_id == branch_id, Enrollment.status != "cancelled")
    ) or Decimal("0")

    total_paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0")))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.branch_id == branch_id)
    ) or Decimal("0")

    branch_faculty = db.scalar(
        select(func.count(User.id)).join(Role).where(User.branch_id == branch_id, Role.name == "Faculty", User.is_active.is_(True))
    ) or 0
    branch_staff = db.scalar(
        select(func.count(User.id)).join(Role).where(User.branch_id == branch_id, Role.name.in_(["Staff", "Counsellor"]), User.is_active.is_(True))
    ) or 0

    # Overdue installments
    today = date.today()
    overdue_query = (
        select(FeeInstallment, FeePlan, Enrollment, Student)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            Batch.branch_id == branch_id,
            FeeInstallment.status != "paid",
            FeeInstallment.due_date <= today,
        )
        .order_by(FeeInstallment.due_date.asc())
        .limit(6)
    )
    overdue_rows = db.execute(overdue_query).all()
    overdue_items = [
        {
            "installment_id": row[0].id,
            "student_name": row[3].full_name,
            "student_phone": row[3].phone or "—",
            "amount": float(row[0].amount),
            "due_date": row[0].due_date.isoformat(),
            "enrollment_code": row[2].enrollment_code,
        }
        for row in overdue_rows
    ]

    return {
        "dashboard_type": "branch_admin",
        "branch_name": branch.name if branch else "Assigned Branch",
        "branch_code": branch.code if branch else "—",
        "branch_students_count": db.scalar(select(func.count(Student.id)).where(Student.branch_id == branch_id, Student.is_active.is_(True))) or 0,
        "branch_batches_count": len(batches),
        "branch_faculty_count": int(branch_faculty),
        "branch_staff_count": int(branch_staff),
        "monthly_collection": get_monthly_collection(db, branch_id),
        "outstanding_balance": float(total_due - total_paid),
        "branch_attendance_rate": get_branch_attendance_rate(db, branch_id),
        "staff_attendance_today": branch_staff_attendance_snapshot(db, branch_id),
        "batches": batch_items,
        "overdue_installments": overdue_items,
        "charts": {
            "revenue_trend": monthly_revenue(db, 6, branch_id),
            "admissions_trend": monthly_admissions(db, 6, branch_id),
            "attendance_trend": attendance_trend(db, 6, branch_id),
            "course_popularity": course_popularity(db, branch_id),
            "fee_aging": fee_aging(db, branch_id),
        },
    }


def build_faculty_dashboard(db: DatabaseSession, current_user: User) -> dict:
    today = date.today()
    batches = db.scalars(
        select(Batch)
        .options(joinedload(Batch.course))
        .where(Batch.faculty_id == current_user.id, Batch.is_active.is_(True))
        .order_by(Batch.start_date.desc())
    ).all()

    my_batch_items = []
    total_students = 0
    batches_marked_today = 0

    for b in batches:
        enrolled = db.scalar(
            select(func.count(Enrollment.id)).where(Enrollment.batch_id == b.id, Enrollment.status == "active")
        ) or 0
        total_students += enrolled

        marked_today = db.scalar(
            select(func.count(Attendance.id))
            .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
            .where(Enrollment.batch_id == b.id, Attendance.attendance_date == today)
        ) or 0
        is_marked = marked_today > 0
        is_running_today = b.start_date <= today and (
            b.end_date is None or b.end_date >= today
        )
        if is_running_today and is_marked:
            batches_marked_today += 1

        my_batch_items.append({
            "id": b.id,
            "name": b.name,
            "code": b.code,
            "course_name": b.course.name if b.course else "Unknown",
            "students_count": int(enrolled),
            "capacity": b.capacity,
            "attendance_marked_today": is_marked,
            "start_date": b.start_date.isoformat() if b.start_date else "",
        })

    # Recent exams in my batches
    batch_ids = [b.id for b in batches]
    recent_exams = []
    if batch_ids:
        exams = db.scalars(
            select(Examination)
            .options(joinedload(Examination.batch), joinedload(Examination.subjects))
            .where(Examination.batch_id.in_(batch_ids))
            .order_by(Examination.exam_date.desc())
            .limit(5)
        ).unique().all()
        for ex in exams:
            recent_exams.append({
                "id": ex.id,
                "name": ex.name,
                "batch_name": ex.batch.name if ex.batch else "Batch",
                "exam_date": ex.exam_date.isoformat(),
                "is_published": ex.is_published,
                "subjects_count": len(ex.subjects),
            })

    # Faculty overall attendance rate in their batches
    att_rate = 0.0
    if batch_ids:
        att_query = (
            select(
                func.count(Attendance.id),
                func.sum(case((Attendance.status.in_(("present", "late", "excused")), 1), else_=0)),
            )
            .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
            .where(Enrollment.batch_id.in_(batch_ids))
        )
        total_att, attended = db.execute(att_query).one()
        total_att = int(total_att or 0)
        attended = int(attended or 0)
        att_rate = round((attended / total_att) * 100, 2) if total_att else 0.0

    return {
        "dashboard_type": "faculty",
        "faculty_name": current_user.full_name,
        "assigned_batches_count": len(batches),
        "total_my_students": total_students,
        "batches_today_count": sum(
            1
            for b in batches
            if b.start_date <= today and (b.end_date is None or b.end_date >= today)
        ),
        "attendance_marked_today_count": batches_marked_today,
        "attendance_rate": att_rate,
        "my_attendance": staff_attendance_snapshot(db, current_user.id),
        "my_batches": my_batch_items,
        "recent_exams": recent_exams,
        "charts": {
            "attendance_trend": attendance_trend(
                db, 6, None, faculty_id=current_user.id
            ),
            "exam_grades": exam_grade_distribution(
                db, branch_id=None, faculty_id=current_user.id
            ),
            "batch_students": batch_students(db, None, faculty_id=current_user.id),
        },
    }


def build_staff_dashboard(db: DatabaseSession, current_user: User) -> dict:
    today = date.today()
    branch_id = current_user.branch_id

    # Today's collections
    today_collection = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0")))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Payment.payment_date == today, Batch.branch_id == branch_id if branch_id else True)
    ) or Decimal("0")

    # Monthly collection
    monthly_collection = get_monthly_collection(db, branch_id)

    # Overdue installments
    overdue_query = (
        select(FeeInstallment, FeePlan, Enrollment, Student)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            FeeInstallment.status != "paid",
            FeeInstallment.due_date <= today,
            Batch.branch_id == branch_id if branch_id else True,
        )
        .order_by(FeeInstallment.due_date.asc())
    )
    overdue_rows = db.execute(overdue_query).all()
    overdue_items = [
        {
            "installment_id": row[0].id,
            "student_name": row[3].full_name,
            "student_phone": row[3].phone or "—",
            "amount": float(row[0].amount),
            "due_date": row[0].due_date.isoformat(),
            "enrollment_code": row[2].enrollment_code,
        }
        for row in overdue_rows[:6]
    ]

    # Recent payments
    payments_query = (
        select(Payment, FeeInstallment, FeePlan, Enrollment, Student)
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.branch_id == branch_id if branch_id else True)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .limit(6)
    )
    payment_rows = db.execute(payments_query).all()
    payment_items = [
        {
            "receipt_number": row[0].receipt_number,
            "student_name": row[4].full_name,
            "amount": float(row[0].amount),
            "payment_method": row[0].payment_method.replace("_", " ").upper(),
            "payment_date": row[0].payment_date.isoformat(),
        }
        for row in payment_rows
    ]

    # My assigned responsibilities
    my_responsibilities = db.scalars(
        select(Responsibility)
        .where(Responsibility.assigned_to_id == current_user.id)
        .order_by(Responsibility.due_date.asc())
        .limit(6)
    ).all()
    resp_items = [
        {
            "id": r.id,
            "title": r.title,
            "department": r.department,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "status": r.status,
        }
        for r in my_responsibilities
    ]

    active_enrollments = db.scalar(
        select(func.count(Enrollment.id))
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Enrollment.status == "active", Batch.branch_id == branch_id if branch_id else True)
    ) or 0

    return {
        "dashboard_type": "staff",
        "staff_name": current_user.full_name,
        "today_collection": float(today_collection),
        "monthly_collection": monthly_collection,
        "pending_installments_count": len(overdue_rows),
        "total_pending_amount": float(sum(r[0].amount for r in overdue_rows)),
        "active_enrollments_count": int(active_enrollments),
        "my_pending_responsibilities_count": len([r for r in my_responsibilities if r.status != "completed"]),
        "recent_payments": payment_items,
        "overdue_installments": overdue_items,
        "my_responsibilities": resp_items,
        "charts": {
            "collection_trend": monthly_revenue(db, 6, branch_id),
            "payment_methods": payment_method_split(db, branch_id),
            "fee_aging": fee_aging(db, branch_id),
            "admissions_trend": monthly_admissions(db, 6, branch_id),
        },
    }


def build_counsellor_dashboard(db: DatabaseSession, current_user: User) -> dict:
    today = date.today()
    branch_id = current_user.branch_id

    total_students = db.scalar(
        select(func.count(Student.id)).where(Student.branch_id == branch_id if branch_id else True, Student.is_active.is_(True))
    ) or 0

    admissions_this_month = db.scalar(
        select(func.count(Enrollment.id))
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            Enrollment.admission_date >= today.replace(day=1),
            Batch.branch_id == branch_id if branch_id else True,
        )
    ) or 0

    my_responsibilities = db.scalars(
        select(Responsibility)
        .where(Responsibility.assigned_to_id == current_user.id)
        .order_by(Responsibility.due_date.asc())
    ).all()

    open_enquiries = db.scalar(
        select(func.count(Enquiry.id)).where(
            Enquiry.branch_id == branch_id if branch_id else True,
            Enquiry.status.not_in(("admitted", "lost")),
        )
    ) or 0

    followups_due = db.scalar(
        select(func.count(Enquiry.id)).where(
            Enquiry.branch_id == branch_id if branch_id else True,
            Enquiry.status.not_in(("admitted", "lost")),
            Enquiry.follow_up_date.is_not(None),
            Enquiry.follow_up_date <= today,
        )
    ) or 0

    conversions_this_month = db.scalar(
        select(func.count(Enquiry.id)).where(
            Enquiry.branch_id == branch_id if branch_id else True,
            Enquiry.status == "admitted",
            Enquiry.converted_at >= today.replace(day=1),
        )
    ) or 0

    # Academic & attendance watchlist (< 75% attendance)
    students_query = (
        select(Student, Enrollment, Batch)
        .join(Enrollment, Student.id == Enrollment.student_id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            Student.branch_id == branch_id if branch_id else True,
            Enrollment.status == "active",
        )
    )
    student_rows = db.execute(students_query).all()
    watchlist = []

    for stu, enr, bat in student_rows:
        att_query = select(
            func.count(Attendance.id),
            func.sum(case((Attendance.status.in_(("present", "late", "excused")), 1), else_=0)),
        ).where(Attendance.enrollment_id == enr.id)
        tot, att = db.execute(att_query).one()
        tot = int(tot or 0)
        att = int(att or 0)
        rate = round((att / tot) * 100, 1) if tot > 0 else 100.0

        if rate < 75.0 or tot == 0:
            watchlist.append({
                "student_id": stu.id,
                "student_name": stu.full_name,
                "student_code": stu.student_code,
                "phone": stu.phone or "—",
                "parent_name": stu.parent_name or "Parent",
                "parent_phone": stu.parent_phone or "—",
                "batch_name": bat.name,
                "attendance_rate": rate,
                "total_classes": tot,
                "attended_classes": att,
            })

    return {
        "dashboard_type": "counsellor",
        "counsellor_name": current_user.full_name,
        "branch_students_count": int(total_students),
        "admissions_this_month": int(admissions_this_month),
        "pending_followups_count": len([r for r in my_responsibilities if r.status != "completed"]),
        "open_enquiries_count": int(open_enquiries),
        "followups_due_count": int(followups_due),
        "conversions_this_month": int(conversions_this_month),
        "low_attendance_students_count": len(watchlist),
        "academic_watchlist": watchlist[:10],
        "my_responsibilities": [
            {
                "id": r.id,
                "title": r.title,
                "department": r.department,
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "status": r.status,
            }
            for r in my_responsibilities[:6]
        ],
        "charts": {
            "enquiry_funnel": enquiry_funnel(db, branch_id),
            "enquiry_sources": enquiry_sources(db, branch_id),
            "admissions_trend": monthly_admissions(db, 6, branch_id),
        },
    }


@router.get("/summary")
def dashboard_summary(
    db: DatabaseSession,
    current_user: User = Depends(DashboardUser),
) -> dict:
    role = current_user.role.name if current_user.role else "Super Admin"

    # Common legacy metrics for compatibility. Every non-admin role is scoped to
    # its assigned branch; course counts stay global because courses are shared
    # reference data across branches.
    branch_id = branch_scope(current_user)
    student_query = select(func.count(Student.id)).where(Student.is_active.is_(True))
    course_query = select(func.count(Course.id)).where(Course.is_active.is_(True))
    batch_query = select(func.count(Batch.id)).where(Batch.is_active.is_(True))
    if branch_id is not None:
        student_query = student_query.where(Student.branch_id == branch_id)
        batch_query = batch_query.where(Batch.branch_id == branch_id)

    monthly_collection = get_monthly_collection(db, branch_id)
    att_rate = get_branch_attendance_rate(db, branch_id)

    # Role specific personalized dashboard builder
    if role == "Super Admin":
        role_dashboard = build_super_admin_dashboard(db, current_user)
    elif role == "Branch Admin":
        role_dashboard = build_branch_admin_dashboard(db, current_user)
    elif role == "Faculty":
        role_dashboard = build_faculty_dashboard(db, current_user)
    elif role == "Staff":
        role_dashboard = build_staff_dashboard(db, current_user)
    elif role == "Counsellor":
        role_dashboard = build_counsellor_dashboard(db, current_user)
    else:
        role_dashboard = {"dashboard_type": "default"}

    return {
        "role_name": role,
        "branch_id": current_user.branch_id,
        "total_students": int(db.scalar(student_query) or 0),
        "active_courses": int(db.scalar(course_query) or 0),
        "active_batches": int(db.scalar(batch_query) or 0),
        "fee_collection": monthly_collection,
        "attendance_rate": att_rate,
        "role_dashboard": role_dashboard,
    }
