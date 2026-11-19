from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import DatabaseSession, require_roles
from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.certificate import Certificate
from app.models.enrollment import Enrollment
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan
from app.models.lms import (
    Assignment,
    AssignmentSubmission,
    CourseModule,
    Lesson,
    LessonProgress,
)
from app.models.parent import ParentStudentLink
from app.models.student import Student
from app.models.user import User
from app.schemas.parent import (
    ParentPortalAssignment,
    ParentPortalAttendance,
    ParentPortalCertificate,
    ParentPortalChild,
    ParentPortalEnrollment,
    ParentPortalResponse,
    ParentPortalResult,
)
from app.services.course_lifecycle import enrollment_course_timing


router = APIRouter(prefix="/api/parent-portal", tags=["Parent Portal"])
ParentUser = require_roles("Parent")


def _attendance_map(
    db: DatabaseSession, student_ids: list[int]
) -> dict[int, tuple[int, int, int, int, int]]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(
            Attendance.enrollment_id,
            func.count(Attendance.id),
            func.sum(case((Attendance.status == "present", 1), else_=0)),
            func.sum(case((Attendance.status == "late", 1), else_=0)),
            func.sum(case((Attendance.status == "absent", 1), else_=0)),
            func.sum(case((Attendance.status == "excused", 1), else_=0)),
        )
        .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
        .where(Enrollment.student_id.in_(student_ids))
        .group_by(Attendance.enrollment_id)
    ).all()
    return {
        row[0]: (
            int(row[1] or 0),
            int(row[2] or 0),
            int(row[3] or 0),
            int(row[4] or 0),
            int(row[5] or 0),
        )
        for row in rows
    }


@router.get("/me", response_model=ParentPortalResponse)
def get_parent_portal(
    db: DatabaseSession,
    current_user: User = Depends(ParentUser),
) -> ParentPortalResponse:
    links = db.scalars(
        select(ParentStudentLink)
        .options(
            joinedload(ParentStudentLink.student).joinedload(Student.branch),
        )
        .where(ParentStudentLink.parent_user_id == current_user.id)
        .order_by(ParentStudentLink.is_primary.desc(), ParentStudentLink.id)
    ).all()
    student_ids = [link.student_id for link in links]
    attendance_map = _attendance_map(db, student_ids)

    # Lesson totals are per course, while completion is per enrollment. Fetch
    # both in bulk so the portal stays fast for families with several children.
    lesson_totals: dict[int, int] = {}
    completed_lessons: dict[int, int] = {}
    all_enrollments = db.execute(
        select(Enrollment.id, Batch.course_id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Enrollment.student_id.in_(student_ids))
    ).all()
    course_ids = {row[1] for row in all_enrollments}
    enrollment_course = {row[0]: row[1] for row in all_enrollments}
    if course_ids:
        total_rows = db.execute(
            select(CourseModule.course_id, func.count(Lesson.id))
            .join(Lesson, Lesson.module_id == CourseModule.id)
            .where(
                CourseModule.course_id.in_(course_ids),
                CourseModule.is_published.is_(True),
                Lesson.is_published.is_(True),
            )
            .group_by(CourseModule.course_id)
        ).all()
        lesson_totals = {row[0]: int(row[1] or 0) for row in total_rows}
    enrollment_ids = list(enrollment_course)
    if enrollment_ids:
        completed_rows = db.execute(
            select(LessonProgress.enrollment_id, func.count(LessonProgress.id))
            .where(
                LessonProgress.enrollment_id.in_(enrollment_ids),
                LessonProgress.status == "completed",
            )
            .group_by(LessonProgress.enrollment_id)
        ).all()
        completed_lessons = {row[0]: int(row[1] or 0) for row in completed_rows}

    children: list[ParentPortalChild] = []
    for link in links:
        student = link.student
        if student is None or not student.is_active:
            continue

        enrollments = db.scalars(
            select(Enrollment)
            .options(
                joinedload(Enrollment.batch).joinedload(Batch.course),
                joinedload(Enrollment.fee_plan)
                .joinedload(FeePlan.installments)
                .joinedload(FeeInstallment.payments),
            )
            .where(Enrollment.student_id == student.id)
            .order_by(Enrollment.admission_date.desc())
        ).unique().all()

        enrollment_payload: list[ParentPortalEnrollment] = []
        attendance_payload: list[ParentPortalAttendance] = []
        for enrollment in enrollments:
            present, late, absent, excused, total = (0, 0, 0, 0, 0)
            stats = attendance_map.get(enrollment.id)
            if stats is not None:
                total, present, late, absent, excused = stats
            # Excused absences do not lower the rate.
            percentage = (
                round(((present + late + excused) / total) * 100, 2)
                if total
                else 0.0
            )

            plan = enrollment.fee_plan
            total_fee = Decimal("0")
            paid = Decimal("0")
            next_due: date | None = None
            if plan is not None:
                total_fee = (
                    plan.total_amount
                    - (plan.discount_amount or Decimal("0"))
                    - (plan.scholarship_amount or Decimal("0"))
                )
                for installment in plan.installments:
                    installment_paid = sum(
                        (payment.amount for payment in installment.payments),
                        Decimal("0"),
                    )
                    paid += installment_paid
                    if (
                        installment.amount - installment_paid > 0
                        and (next_due is None or installment.due_date < next_due)
                    ):
                        next_due = installment.due_date
            balance = total_fee - paid
            fee_status = "Cleared"
            if balance > 0:
                if next_due is not None and next_due < date.today():
                    fee_status = "Overdue"
                elif next_due is not None:
                    fee_status = "Due soon"
                else:
                    fee_status = "Pending"

            end_date, days_remaining, completed = enrollment_course_timing(enrollment)
            course_id = enrollment.batch.course_id
            total_lessons = lesson_totals.get(course_id, 0)
            done_lessons = completed_lessons.get(enrollment.id, 0)
            progress_percent = (
                round((done_lessons / total_lessons) * 100, 2) if total_lessons else 0.0
            )
            enrollment_payload.append(
                ParentPortalEnrollment(
                    enrollment_id=enrollment.id,
                    enrollment_code=enrollment.enrollment_code,
                    course_name=enrollment.batch.course.name,
                    batch_name=enrollment.batch.name,
                    status=enrollment.status,
                    admission_date=enrollment.admission_date,
                    course_end_date=end_date,
                    days_remaining=days_remaining,
                    course_completed=completed,
                    attendance_percentage=percentage,
                    progress_percent=progress_percent,
                    completed_lessons=done_lessons,
                    total_lessons=total_lessons,
                    total_fee=total_fee,
                    total_paid=paid,
                    balance=balance,
                    next_due_date=next_due,
                    fee_status=fee_status,
                )
            )
            attendance_payload.append(
                ParentPortalAttendance(
                    enrollment_code=enrollment.enrollment_code,
                    total=total,
                    present=present,
                    late=late,
                    absent=absent,
                    excused=excused,
                    percentage=percentage,
                )
            )

        result_rows = db.execute(
            select(
                Examination.name,
                Examination.exam_date,
                ExamSubject.name,
                ExamMark.marks_obtained,
                ExamSubject.max_marks,
                ExamMark.grade,
            )
            .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
            .join(Examination, ExamSubject.examination_id == Examination.id)
            .join(Enrollment, ExamMark.enrollment_id == Enrollment.id)
            .where(
                Enrollment.student_id == student.id,
                Examination.is_published.is_(True),
            )
            .order_by(Examination.exam_date.desc(), ExamSubject.name)
        ).all()
        results = [
            ParentPortalResult(
                examination=row[0],
                exam_date=row[1],
                subject=row[2],
                marks_obtained=row[3],
                maximum_marks=row[4],
                grade=row[5],
            )
            for row in result_rows
        ]

        assignment_rows = db.scalars(
            select(Assignment)
            .where(
                Assignment.course_id.in_(
                    {enrollment.batch.course_id for enrollment in enrollments}
                ),
                Assignment.is_published.is_(True),
            )
            .order_by(Assignment.due_date, Assignment.id)
        ).all()
        assignment_ids = [assignment.id for assignment in assignment_rows]
        submissions = {}
        if assignment_ids:
            submissions = {
                submission.assignment_id: submission
                for submission in db.scalars(
                    select(AssignmentSubmission).where(
                        AssignmentSubmission.enrollment_id.in_(
                            [enrollment.id for enrollment in enrollments]
                        ),
                        AssignmentSubmission.assignment_id.in_(assignment_ids),
                    )
                ).all()
            }
        assignments = []
        for assignment in assignment_rows:
            submission = submissions.get(assignment.id)
            if submission is None:
                status = (
                    "Overdue"
                    if assignment.due_date is not None
                    and assignment.due_date < date.today()
                    else "Pending"
                )
            else:
                status = submission.status.capitalize()
            course_name = next(
                (
                    enrollment.batch.course.name
                    for enrollment in enrollments
                    if enrollment.batch.course_id == assignment.course_id
                ),
                "—",
            )
            assignments.append(
                ParentPortalAssignment(
                    assignment_id=assignment.id,
                    title=assignment.title,
                    course_name=course_name,
                    due_date=assignment.due_date,
                    status=status,
                    submitted_at=submission.submitted_at if submission else None,
                    marks_obtained=submission.marks if submission else None,
                    maximum_marks=assignment.max_marks,
                    grade=submission.grade if submission else None,
                    feedback=submission.feedback if submission else None,
                )
            )

        certificates = [
            ParentPortalCertificate(
                id=certificate.id,
                certificate_number=certificate.certificate_number,
                verification_code=certificate.verification_code,
                document_type=certificate.document_type,
                issue_date=certificate.issue_date,
                grade=certificate.grade,
                percentage=certificate.percentage,
                is_valid=certificate.is_valid,
            )
            for certificate in db.scalars(
                select(Certificate)
                .join(Enrollment)
                .where(Enrollment.student_id == student.id)
                .order_by(Certificate.issue_date.desc())
            ).all()
        ]

        children.append(
            ParentPortalChild(
                student_id=student.id,
                student_code=student.student_code,
                full_name=student.full_name,
                photo_url=student.photo_url,
                branch_name=student.branch.name if student.branch else "—",
                relationship=link.relationship,
                is_primary=link.is_primary,
                enrollments=enrollment_payload,
                attendance=attendance_payload,
                results=results,
                assignments=assignments,
                certificates=certificates,
            )
        )

    if not children:
        raise HTTPException(
            status_code=403,
            detail="No student profiles are linked to this parent account yet",
        )

    return ParentPortalResponse(
        parent_name=current_user.full_name,
        email=current_user.email,
        phone=current_user.phone,
        children=children,
    )
