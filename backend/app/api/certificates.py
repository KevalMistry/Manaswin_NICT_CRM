from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    get_current_user,
    has_module_access,
    require_module,
    require_roles,
)
from app.core.config import FRONTEND_URL
from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.lms import Assignment, AssignmentSubmission
from app.models.online_exam import ExamAttempt, OnlineExam
from app.models.parent import ParentStudentLink
from app.models.student import Student
from app.models.user import User
from app.schemas.certificate import (
    AssignmentEligibility,
    AttendanceEligibility,
    CertificateAutoIssueItem,
    CertificateAutoIssueRequest,
    CertificateAutoIssueResponse,
    CertificateCreate,
    CertificateEligibilityResponse,
    CertificateResponse,
    CertificateVerificationResponse,
    CourseTimingEligibility,
    ExamEligibility,
    FeeEligibility,
    OnlineExamEligibility,
)
from app.services.course_lifecycle import enrollment_course_timing
from app.services.certificate_document import (
    CertificateDocumentData,
    SubjectResult,
    render_certificate_document,
)


router = APIRouter(prefix="/api/certificates", tags=["Certificates"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff", "Faculty", "Counsellor")
AutoIssueUser = require_roles("Super Admin", "Branch Admin")
CertificatesAccess = require_module("certificates")


def get_enrollment(db: DatabaseSession, enrollment_id: int, current_user) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment)
        .options(
            joinedload(Enrollment.batch).joinedload(Batch.course),
            joinedload(Enrollment.student),
        )
        .where(Enrollment.id == enrollment_id)
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    check_branch_access(current_user, enrollment.batch.branch_id)
    return enrollment


def result_summary(db: DatabaseSession, enrollment_id: int) -> tuple[Decimal, Decimal, str | None, bool]:
    rows = db.execute(
        select(ExamMark, ExamSubject)
        .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
        .join(Examination, ExamSubject.examination_id == Examination.id)
        .where(ExamMark.enrollment_id == enrollment_id, Examination.is_published.is_(True))
    ).all()
    total = sum((row[0].marks_obtained for row in rows), Decimal("0"))
    maximum = sum((row[1].max_marks for row in rows), Decimal("0"))
    batch_id = db.scalar(select(Enrollment.batch_id).where(Enrollment.id == enrollment_id))
    published_subject_ids = set(
        db.scalars(
            select(ExamSubject.id)
            .join(Examination, ExamSubject.examination_id == Examination.id)
            .where(
                Examination.batch_id == batch_id,
                Examination.is_published.is_(True),
            )
        ).all()
    )
    marked_subject_ids = {row[0].exam_subject_id for row in rows}
    complete = published_subject_ids == marked_subject_ids
    if not rows or maximum <= 0:
        # No marks yet, or every published subject has a zero maximum. There
        # is no meaningful percentage or grade to report in either case.
        return total, maximum, None, complete
    ratio = total / maximum
    if any(row[0].grade == "F" for row in rows):
        grade = "F"
    elif ratio >= Decimal("0.9"):
        grade = "A+"
    elif ratio >= Decimal("0.8"):
        grade = "A"
    elif ratio >= Decimal("0.7"):
        grade = "B+"
    elif ratio >= Decimal("0.6"):
        grade = "B"
    elif ratio >= Decimal("0.5"):
        grade = "C"
    else:
        grade = "D"
    return total, maximum, grade, complete


CERTIFICATE_MIN_ATTENDANCE = 75.0


def attendance_eligibility(db: DatabaseSession, enrollment_id: int) -> AttendanceEligibility:
    rows = db.execute(
        select(Attendance.status, func.count(Attendance.id))
        .where(Attendance.enrollment_id == enrollment_id)
        .group_by(Attendance.status)
    ).all()
    counts = {status: int(count) for status, count in rows}
    present = counts.get("present", 0)
    late = counts.get("late", 0)
    excused = counts.get("excused", 0)
    absent = counts.get("absent", 0)
    recorded = present + late + excused + absent
    # Excused absences were authorised in advance, so they do not count against
    # the student's attendance percentage. Keep them in the denominator and
    # count them as attended so excused days are neutral, not penalising.
    attended = present + late + excused
    percentage = round((attended / recorded) * 100, 2) if recorded else 0.0
    if recorded == 0:
        met = True
        note = "No student attendance has been recorded yet, so attendance is not a blocker."
    else:
        met = percentage >= CERTIFICATE_MIN_ATTENDANCE
        note = None
    return AttendanceEligibility(
        recorded_days=recorded,
        present_days=present,
        late_days=late,
        excused_days=excused,
        attended_days=attended,
        percentage=percentage,
        minimum_percentage=CERTIFICATE_MIN_ATTENDANCE,
        met=met,
        note=note,
    )


def fee_eligibility(db: DatabaseSession, enrollment_id: int) -> FeeEligibility:
    plan = (
        db.execute(
            select(FeePlan)
            .options(
                joinedload(FeePlan.installments).joinedload(FeeInstallment.payments)
            )
            .where(FeePlan.enrollment_id == enrollment_id)
        )
        .unique()
        .scalars()
        .first()
    )
    if plan is None:
        return FeeEligibility(
            has_fee_plan=False,
            total_fee=Decimal("0"),
            paid_amount=Decimal("0"),
            outstanding_amount=Decimal("0"),
            met=True,
        )
    total_fee = plan.total_amount - plan.discount_amount - plan.scholarship_amount
    paid = sum(
        (payment.amount for installment in plan.installments for payment in installment.payments),
        Decimal("0"),
    )
    outstanding = max(total_fee - paid, Decimal("0"))
    return FeeEligibility(
        has_fee_plan=True,
        total_fee=total_fee,
        paid_amount=paid,
        outstanding_amount=outstanding,
        met=outstanding <= 0,
    )


def assignment_eligibility(db: DatabaseSession, enrollment: Enrollment) -> AssignmentEligibility:
    """Require every published course assignment to be submitted.

    Installations that have not started using the LMS are not penalised: when a
    course has no published assignments the check is simply not tracked.
    """
    published = int(
        db.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.course_id == enrollment.batch.course_id,
                Assignment.is_published.is_(True),
            )
        )
        or 0
    )
    if published == 0:
        return AssignmentEligibility(
            tracked=False,
            met=True,
            note="No assignments have been published for this course, so assignment tracking is not a blocker.",
        )
    submitted = int(
        db.scalar(
            select(func.count(AssignmentSubmission.id))
            .join(Assignment, AssignmentSubmission.assignment_id == Assignment.id)
            .where(
                AssignmentSubmission.enrollment_id == enrollment.id,
                Assignment.course_id == enrollment.batch.course_id,
                Assignment.is_published.is_(True),
            )
        )
        or 0
    )
    return AssignmentEligibility(
        tracked=True,
        met=submitted >= published,
        note=f"{submitted} of {published} published assignment(s) submitted.",
    )


def online_exam_eligibility(
    db: DatabaseSession, enrollment: Enrollment
) -> OnlineExamEligibility:
    """Require a passing attempt for every published online exam.

    Courses that have not scheduled online exams are not penalised.
    """
    exam_ids = select(OnlineExam.id).where(
        OnlineExam.course_id == enrollment.batch.course_id,
        OnlineExam.is_published.is_(True),
        or_(
            OnlineExam.batch_id.is_(None),
            OnlineExam.batch_id == enrollment.batch_id,
        ),
    )
    total = int(db.scalar(select(func.count()).select_from(exam_ids.subquery())) or 0)
    if total == 0:
        return OnlineExamEligibility(
            tracked=False,
            total_exams=0,
            passed_exams=0,
            met=True,
            note="No online exams have been published for this course, so they are not a blocker.",
        )
    passed = int(
        db.scalar(
            select(func.count(func.distinct(ExamAttempt.exam_id))).where(
                ExamAttempt.enrollment_id == enrollment.id,
                ExamAttempt.exam_id.in_(exam_ids),
                ExamAttempt.status == "submitted",
                ExamAttempt.passed.is_(True),
            )
        )
        or 0
    )
    return OnlineExamEligibility(
        tracked=True,
        total_exams=total,
        passed_exams=passed,
        met=passed >= total,
        note=f"{passed} of {total} published online exam(s) passed.",
    )


def build_eligibility(
    db: DatabaseSession,
    enrollment: Enrollment,
    document_type: str,
    ignore_course_timing: bool = False,
) -> CertificateEligibilityResponse:
    attendance = attendance_eligibility(db, enrollment.id)
    fees = fee_eligibility(db, enrollment.id)
    total, maximum, grade, complete = result_summary(db, enrollment.id)
    end_date, days_remaining, course_completed = enrollment_course_timing(enrollment)
    timing_note = None
    if end_date is None:
        timing_note = "This batch has no end date and its course duration is not configured."
    course_timing = CourseTimingEligibility(
        course_duration_months=int(enrollment.batch.course.duration_months),
        course_end_date=end_date,
        days_remaining=days_remaining,
        completed=course_completed,
        met=course_completed,
        note=timing_note,
    )

    published_subjects = int(
        db.scalar(
            select(func.count(ExamSubject.id))
            .join(Examination, ExamSubject.examination_id == Examination.id)
            .where(
                Examination.batch_id == enrollment.batch_id,
                Examination.is_published.is_(True),
            )
        )
        or 0
    )
    marked_subjects = int(
        db.scalar(
            select(func.count(func.distinct(ExamMark.exam_subject_id)))
            .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
            .join(Examination, ExamSubject.examination_id == Examination.id)
            .where(
                ExamMark.enrollment_id == enrollment.id,
                Examination.is_published.is_(True),
            )
        )
        or 0
    )
    passed = grade is not None and grade != "F"
    exams = ExamEligibility(
        published_subjects=published_subjects,
        marked_subjects=marked_subjects,
        all_marks_recorded=complete,
        grade=grade,
        passed=passed,
        met=complete and passed,
    )
    assignments = assignment_eligibility(db, enrollment)
    online_exams = online_exam_eligibility(db, enrollment)

    blockers: list[str] = []
    if enrollment.status not in {"active", "completed"}:
        blockers.append("Enrollment is not active or completed.")
    if document_type == "certificate":
        if not course_timing.met and not ignore_course_timing:
            if course_timing.course_end_date is None:
                blockers.append(
                    "The batch needs an end date (or the course needs a duration) before a certificate can be issued."
                )
            else:
                blockers.append(
                    f"The course ends on {course_timing.course_end_date.isoformat()} "
                    f"({course_timing.days_remaining} days remaining). Certificates are issued at the end of the course."
                )
        if not attendance.met:
            blockers.append(
                f"Attendance is {attendance.percentage:.2f}%; at least "
                f"{CERTIFICATE_MIN_ATTENDANCE:.0f}% is required."
            )
        if not assignments.met:
            blockers.append(
                "Every published course assignment must be submitted before a certificate can be issued."
            )
        if not online_exams.met:
            blockers.append(
                "Every published online exam must be passed before a certificate can be issued."
            )
        if not fees.met:
            blockers.append(
                f"Outstanding fees of INR {fees.outstanding_amount:,.2f} must be cleared."
            )
        if not complete:
            blockers.append(
                "Marks for every subject of the published examinations must be recorded first."
            )
        elif grade is None:
            blockers.append("Marks must be published before issuing a certificate.")
        elif not passed:
            blockers.append("Student has not passed the published examinations.")
    else:
        if not complete:
            blockers.append(
                "Marks for every subject of the published examinations must be recorded first."
            )
        elif grade is None:
            blockers.append("Marks must be published before issuing a marksheet.")

    return CertificateEligibilityResponse(
        enrollment_id=enrollment.id,
        enrollment_status=enrollment.status,
        document_type=document_type,
        student_name=enrollment.student.full_name,
        student_code=enrollment.student.student_code,
        course_name=enrollment.batch.course.name,
        course_timing=course_timing,
        attendance=attendance,
        fees=fees,
        exams=exams,
        assignments=assignments,
        online_exams=online_exams,
        eligible=not blockers,
        blockers=blockers,
    )


@router.get(
    "/eligibility/{enrollment_id}",
    response_model=CertificateEligibilityResponse,
    dependencies=[Depends(CertificatesAccess)],
)
def certificate_eligibility(
    enrollment_id: int,
    db: DatabaseSession,
    document_type: str = Query(default="certificate", pattern=r"^(certificate|marksheet)$"),
    current_user=Depends(AdminUser),
) -> CertificateEligibilityResponse:
    enrollment = get_enrollment(db, enrollment_id, current_user)
    return build_eligibility(db, enrollment, document_type)


@router.post("", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(CertificatesAccess)])
def issue_certificate(
    payload: CertificateCreate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> Certificate:
    enrollment = get_enrollment(db, payload.enrollment_id, current_user)
    if enrollment.status not in {"active", "completed"}:
        raise HTTPException(status_code=400, detail="Enrollment is not eligible")
    if db.scalar(
        select(Certificate).where(
            Certificate.enrollment_id == enrollment.id,
            Certificate.document_type == payload.document_type,
        )
    ):
        raise HTTPException(status_code=409, detail="Document already issued")

    total, maximum, grade, complete = result_summary(db, enrollment.id)
    end_date, _, course_completed = enrollment_course_timing(enrollment)
    if payload.document_type == "certificate":
        eligibility = build_eligibility(db, enrollment, payload.document_type)
        if not eligibility.eligible:
            early_override = (
                payload.allow_early
                and current_user.role.name == "Super Admin"
                and not course_completed
            )
            if not early_override:
                raise HTTPException(
                    status_code=400,
                    detail=" ".join(eligibility.blockers),
                )
            relaxed = build_eligibility(
                db, enrollment, payload.document_type, ignore_course_timing=True
            )
            if not relaxed.eligible:
                raise HTTPException(
                    status_code=400,
                    detail=" ".join(relaxed.blockers),
                )
    else:
        if not complete:
            raise HTTPException(
                status_code=400,
                detail="Marks for every subject of the published examinations must be recorded first",
            )
        if grade is None:
            raise HTTPException(status_code=400, detail="Marks must be published before issuing a marksheet")

    document = Certificate(
        certificate_number=f"{payload.document_type.upper()[:3]}-{date.today().year}-{uuid4().hex[:10].upper()}",
        verification_code=uuid4().hex,
        issue_date=date.today(),
        grade=grade,
        percentage=float((total / maximum) * 100) if maximum else None,
        enrollment_id=enrollment.id,
        document_type=payload.document_type,
        digital_signature=payload.digital_signature,
    )
    db.add(document)
    # Reaching the end of the course is the natural completion signal. Issuing
    # the end-of-course certificate also closes the enrollment.
    if payload.document_type == "certificate" and course_completed and enrollment.status == "active":
        enrollment.status = "completed"
    db.commit()
    db.refresh(document)
    return document


def auto_issue_documents(
    db: DatabaseSession,
    *,
    document_type: str = "certificate",
    dry_run: bool = False,
    branch_id: int | None = None,
    digital_signature: str | None = None,
) -> CertificateAutoIssueResponse:
    """Issue documents for finished courses and complete eligible enrollments.

    A course that has ended is scanned for an end-of-course document. The
    enrollment is marked completed only when a new certificate is issued, so
    students who are not yet eligible stay active and are retried later.

    This is safe to run repeatedly: already-issued documents are skipped, and
    ``dry_run`` previews the work without changing the database. The endpoint
    and the daily automation loop both call this helper so certificate rules
    stay in one place.
    """
    tomorrow = date.today() + timedelta(days=1)
    query = (
        select(Enrollment)
        .options(
            joinedload(Enrollment.batch).joinedload(Batch.course),
            joinedload(Enrollment.student),
        )
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(
            Enrollment.status.in_(("active", "completed")),
            # A course is due when its end date is today or earlier. Using the
            # next day as the upper bound keeps the comparison date-only.
            Batch.end_date.is_(None) | (Batch.end_date < tomorrow),
        )
        .order_by(Enrollment.id)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    enrollments = db.scalars(query).unique().all()

    scanned = len(enrollments)
    completed_count = 0
    issued_count = 0
    skipped_count = 0
    items: list[CertificateAutoIssueItem] = []

    for enrollment in enrollments:
        end_date, _, course_completed = enrollment_course_timing(enrollment)
        if not course_completed:
            continue
        existing = db.scalar(
            select(Certificate).where(
                Certificate.enrollment_id == enrollment.id,
                Certificate.document_type == document_type,
            )
        )
        action: str
        detail: str | None = None
        if existing is not None:
            action = "skipped"
            detail = "Document already issued."
            skipped_count += 1
        else:
            eligibility = build_eligibility(db, enrollment, document_type)
            if not eligibility.eligible:
                action = "skipped"
                detail = " ".join(eligibility.blockers)
                skipped_count += 1
            else:
                total, maximum, grade, _ = result_summary(db, enrollment.id)
                certificate = Certificate(
                    certificate_number=(
                        f"{document_type.upper()[:3]}-{date.today().year}-"
                        f"{uuid4().hex[:10].upper()}"
                    ),
                    verification_code=uuid4().hex,
                    issue_date=date.today(),
                    grade=grade,
                    percentage=float((total / maximum) * 100) if maximum else None,
                    enrollment_id=enrollment.id,
                    document_type=document_type,
                    digital_signature=digital_signature,
                )
                db.add(certificate)
                action = "issued"
                detail = certificate.certificate_number
                issued_count += 1
        if (
            document_type == "certificate"
            and action == "issued"
            and enrollment.status == "active"
        ):
            # Mirror the manual issue flow: only a freshly issued end-of-course
            # certificate completes the enrollment. Ineligible or already-issued
            # rows must stay active so they can be retried later.
            enrollment.status = "completed"
            completed_count += 1
            detail = f"{detail or ''} Enrollment marked completed.".strip()
        items.append(
            CertificateAutoIssueItem(
                enrollment_id=enrollment.id,
                student_name=enrollment.student.full_name,
                course_name=enrollment.batch.course.name,
                course_end_date=end_date,
                action=action,
                detail=detail,
            )
        )

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return CertificateAutoIssueResponse(
        scanned=scanned,
        completed_enrollments=completed_count,
        issued=issued_count,
        skipped=skipped_count,
        dry_run=dry_run,
        items=items,
    )


@router.post(
    "/auto-issue",
    response_model=CertificateAutoIssueResponse,
    dependencies=[Depends(CertificatesAccess)],
)
def auto_issue_certificates(
    payload: CertificateAutoIssueRequest,
    db: DatabaseSession,
    current_user=Depends(AutoIssueUser),
) -> CertificateAutoIssueResponse:
    """Complete finished courses and issue documents for eligible students.

    This is safe to run repeatedly: already-issued documents are skipped, and
    ``dry_run`` previews the work without changing the database. Wire this to
    a daily scheduler to make end-of-course certificates fully automatic.
    """
    return auto_issue_documents(
        db,
        document_type=payload.document_type,
        dry_run=payload.dry_run,
        branch_id=branch_scope(current_user),
        digital_signature=payload.digital_signature,
    )


@router.get("", response_model=list[CertificateResponse], dependencies=[Depends(CertificatesAccess)])
def list_certificates(
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> list[Certificate]:
    query = select(Certificate).join(Enrollment).join(Batch)
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Batch.branch_id == scope)
    return list(db.scalars(query.order_by(Certificate.issue_date.desc())).all())


@router.get("/verify/{verification_code}", response_model=CertificateVerificationResponse)
def verify_certificate(
    verification_code: str,
    db: DatabaseSession,
) -> CertificateVerificationResponse:
    certificate = db.scalar(
        select(Certificate)
        .options(
            joinedload(Certificate.enrollment)
            .joinedload(Enrollment.student),
            joinedload(Certificate.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.course),
            joinedload(Certificate.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.branch),
        )
        .where(Certificate.verification_code == verification_code)
    )
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return CertificateVerificationResponse(
        valid=certificate.is_valid,
        certificate_number=certificate.certificate_number,
        document_type=certificate.document_type,
        issue_date=certificate.issue_date,
        student_name=certificate.enrollment.student.full_name,
        student_code=certificate.enrollment.student.student_code,
        course_name=certificate.enrollment.batch.course.name,
        branch_name=certificate.enrollment.batch.branch.name,
        grade=certificate.grade,
        percentage=certificate.percentage,
    )


@router.get("/{certificate_id}/document")
def get_certificate_document(
    certificate_id: int,
    db: DatabaseSession,
    download: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Render an issued certificate or marksheet as a PDF.

    Staff and admins use the certificates module and are limited to their
    branch. A student may open only the documents attached to their own
    student profile. The same endpoint powers both the in-app preview and the
    download button; ``download=true`` switches the disposition to attachment.
    """
    certificate = db.scalar(
        select(Certificate)
        .options(
            joinedload(Certificate.enrollment).joinedload(Enrollment.student),
            joinedload(Certificate.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.course),
            joinedload(Certificate.enrollment)
            .joinedload(Enrollment.batch)
            .joinedload(Batch.branch),
        )
        .where(Certificate.id == certificate_id)
    )
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")

    enrollment = certificate.enrollment
    student = enrollment.student
    batch = enrollment.batch
    branch = batch.branch

    if current_user.role.name == "Student":
        # Do not reveal whether another student's document exists.
        if student.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Certificate not found")
    elif current_user.role.name == "Parent":
        # Parents may only download documents for the children linked to their
        # own account, and should not be able to probe for other students.
        link = db.scalar(
            select(ParentStudentLink.id).where(
                ParentStudentLink.parent_user_id == current_user.id,
                ParentStudentLink.student_id == student.id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Certificate not found")
    else:
        if not has_module_access(current_user, db, "certificates"):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your role ({current_user.role.name}) does not have permission "
                    "to access the 'certificates' module."
                ),
            )
        check_branch_access(current_user, batch.branch_id)

    subjects: list[SubjectResult] = []
    if certificate.document_type == "marksheet":
        rows = db.execute(
            select(
                Examination.name,
                ExamSubject.name,
                ExamMark.marks_obtained,
                ExamSubject.max_marks,
                ExamMark.grade,
            )
            .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
            .join(Examination, ExamSubject.examination_id == Examination.id)
            .where(
                ExamMark.enrollment_id == enrollment.id,
                Examination.is_published.is_(True),
            )
            .order_by(Examination.exam_date, Examination.name, ExamSubject.name)
        ).all()
        subjects = [
            SubjectResult(
                examination=row[0],
                subject=row[1],
                marks_obtained=float(row[2]),
                maximum_marks=float(row[3]),
                grade=row[4],
            )
            for row in rows
        ]

    verification_url = (
        f"{FRONTEND_URL}/verify-certificate?code={certificate.verification_code}"
    )
    pdf_bytes = render_certificate_document(
        CertificateDocumentData(
            document_type=certificate.document_type,
            certificate_number=certificate.certificate_number,
            verification_code=certificate.verification_code,
            issue_date=certificate.issue_date,
            grade=certificate.grade,
            percentage=certificate.percentage,
            digital_signature=certificate.digital_signature,
            is_valid=certificate.is_valid,
            student_name=student.full_name,
            student_code=student.student_code,
            course_name=batch.course.name,
            course_duration_months=batch.course.duration_months,
            batch_name=batch.name,
            branch_name=branch.name,
            branch_address=branch.address,
            branch_phone=branch.phone,
            branch_email=branch.email,
            certificate_title=branch.certificate_title,
            marksheet_title=branch.marksheet_title,
            primary_color=branch.certificate_primary_color,
            accent_color=branch.certificate_accent_color,
            html_template=(
                branch.certificate_template
                if certificate.document_type == "certificate"
                else branch.marksheet_template
            ),
            admission_date=enrollment.admission_date,
            verification_url=verification_url,
            subjects=subjects,
        )
    )

    filename = f"{certificate.certificate_number}.pdf"
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{certificate_id}", response_model=CertificateResponse, dependencies=[Depends(CertificatesAccess)])
def get_certificate(
    certificate_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> Certificate:
    certificate = db.scalar(
        select(Certificate)
        .options(joinedload(Certificate.enrollment).joinedload(Enrollment.batch))
        .where(Certificate.id == certificate_id)
    )
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    check_branch_access(current_user, certificate.enrollment.batch.branch_id)
    return certificate
