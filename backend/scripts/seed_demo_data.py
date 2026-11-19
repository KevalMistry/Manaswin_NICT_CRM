from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.services.permissions import ensure_permissions_seeded
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.attendance import Attendance
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.parent import ParentStudentLink
from app.models.responsibility import PerformanceReview, Responsibility
from app.models.role import Role
from app.models.student import Student
from app.models.user import User


DEMO_PASSWORD = "User123@"
TODAY = date.today()
DEMO_ROLES = {
    "Super Admin": "Full access to the institute management system.",
    "Branch Admin": "Manages one or more assigned branches.",
    "Faculty": "Manages classes, attendance, assignments, and examinations.",
    "Student": "Views courses, fees, attendance, results, and certificates.",
    "Staff": "Manages assigned institute responsibilities and operational work.",
    "Counsellor": "Manages student counselling and follow-up responsibilities.",
    "Parent": "Views linked student progress, attendance, fees, and results.",
}
DEMO_USERS = {
    "demo.superadmin@nictdemo.com": ("Demo Super Admin", "Super Admin"),
    "demo.branchadmin@nictdemo.com": ("Demo Branch Admin", "Branch Admin"),
    "demo.faculty@nictdemo.com": ("Demo Faculty", "Faculty"),
    "demo.staff@nictdemo.com": ("Demo Staff", "Staff"),
    "demo.counsellor@nictdemo.com": ("Demo Counsellor", "Counsellor"),
    "demo.student@nictdemo.com": ("Demo Student", "Student"),
    "demo.parent@nictdemo.com": ("Demo Parent", "Parent"),
}


def get_or_create_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name, description=DEMO_ROLES[name])
        db.add(role)
        db.flush()
    return role



def get_or_create_student(db, code: str, **values) -> Student:
    student = db.scalar(select(Student).where(Student.student_code == code))
    if student is None:
        student = Student(student_code=code, **values)
        db.add(student)
        db.flush()
    return student


def get_or_create_course(db, code: str, **values) -> Course:
    course = db.scalar(select(Course).where(Course.code == code))
    if course is None:
        course = Course(code=code, **values)
        db.add(course)
        db.flush()
    return course


def get_or_create_batch(db, code: str, **values) -> Batch:
    batch = db.scalar(select(Batch).where(Batch.code == code))
    if batch is None:
        batch = Batch(code=code, **values)
        db.add(batch)
        db.flush()
    return batch


def get_or_create_enrollment(db, code: str, **values) -> Enrollment:
    enrollment = db.scalar(select(Enrollment).where(Enrollment.enrollment_code == code))
    if enrollment is None:
        enrollment = Enrollment(enrollment_code=code, **values)
        db.add(enrollment)
        db.flush()
    return enrollment


def get_or_create_enquiry(db, code: str, **values) -> Enquiry:
    enquiry = db.scalar(select(Enquiry).where(Enquiry.enquiry_code == code))
    if enquiry is None:
        enquiry = Enquiry(enquiry_code=code, **values)
        db.add(enquiry)
        db.flush()
    return enquiry


def seed_demo_data() -> None:
    with SessionLocal() as db:
        branch = db.scalar(select(Branch).where(Branch.code == "VAPI"))
        if branch is None:
            branch = Branch(
                name="Manaswin NICT Vapi",
                code="VAPI",
                address="GIDC Road, Vapi, Gujarat",
                phone="+91 98765 43210",
                email="manaswinvapi@gmail.com",
            )
            db.add(branch)
            db.flush()

        roles = {name: get_or_create_role(db, name) for name in DEMO_ROLES}
        ensure_permissions_seeded(db)

        users = {
            user.email: user
            for user in db.scalars(
                select(User).where(User.email.in_(DEMO_USERS))
            ).all()
        }
        for email, (full_name, role_name) in DEMO_USERS.items():
            if email in users:
                continue
            user = User(
                full_name=full_name,
                email=email,
                hashed_password=hash_password(DEMO_PASSWORD),
                role_id=roles[role_name].id,
                branch_id=None if role_name == "Super Admin" else branch.id,
            )
            db.add(user)
            db.flush()
            users[email] = user
        for email, user in users.items():
            # Never move or reactivate an existing account: branch assignments
            # and deactivation are operational data, not seed defaults.
            if (
                email != "demo.superadmin@nictdemo.com"
                and user.branch_id is None
            ):
                user.branch_id = branch.id

        faculty = users["demo.faculty@nictdemo.com"]
        staff = users["demo.staff@nictdemo.com"]
        counsellor = users["demo.counsellor@nictdemo.com"]
        student_user = users["demo.student@nictdemo.com"]
        parent_user = users["demo.parent@nictdemo.com"]

        student = db.scalar(select(Student).where(Student.user_id == student_user.id))
        if student is None:
            student = get_or_create_student(
                db,
                "STU-DEMO-001",
                full_name="Demo Student",
                email=student_user.email,
                phone="+91 98765 40001",
                qualification="12th pass",
                skill_level="Intermediate",
                parent_name="Demo Parent",
                parent_phone="+91 98765 40002",
                address="Vapi, Gujarat",
                branch_id=branch.id,
            )
            student.user_id = student_user.id
        elif student.branch_id is None:
            student.branch_id = branch.id

        parent_link = db.scalar(
            select(ParentStudentLink).where(
                ParentStudentLink.parent_user_id == parent_user.id,
                ParentStudentLink.student_id == student.id,
            )
        )
        if parent_link is None:
            db.add(
                ParentStudentLink(
                    parent_user_id=parent_user.id,
                    student_id=student.id,
                    relationship="Parent",
                    is_primary=True,
                )
            )

        second_student = get_or_create_student(
            db,
            "STU-DEMO-002",
            full_name="Aarav Mehta",
            email="aarav.mehta@nictdemo.com",
            phone="+91 98765 40003",
            qualification="12th pass",
            skill_level="Beginner",
            parent_name="Rakesh Mehta",
            parent_phone="+91 98765 40004",
            address="Vapi, Gujarat",
            branch_id=branch.id,
        )

        third_student = get_or_create_student(
            db,
            "STU-DEMO-003",
            full_name="Diya Shah",
            email="diya.shah@nictdemo.com",
            phone="+91 98765 40005",
            qualification="Graduate",
            skill_level="Advanced",
            parent_name="Nilesh Shah",
            parent_phone="+91 98765 40006",
            address="Vapi, Gujarat",
            branch_id=branch.id,
        )

        python_course = get_or_create_course(
            db,
            "PYTHON-01",
            name="Full Stack Python Development",
            description="Python, FastAPI, SQL, React, and deployment fundamentals.",
            duration_months=6,
            fee_amount=Decimal("60000"),
        )
        data_course = get_or_create_course(
            db,
            "DATA-01",
            name="Data Analytics",
            description="Spreadsheets, SQL, Python analytics, and visualization.",
            duration_months=4,
            fee_amount=Decimal("45000"),
        )

        python_batch = get_or_create_batch(
            db,
            "PYTHON-OCT-26",
            name="Python October 2026",
            course_id=python_course.id,
            branch_id=branch.id,
            faculty_id=faculty.id,
            start_date=date(2026, 10, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        data_batch = get_or_create_batch(
            db,
            "DATA-OCT-26",
            name="Data Analytics October 2026",
            course_id=data_course.id,
            branch_id=branch.id,
            faculty_id=faculty.id,
            start_date=date(2026, 10, 1),
            end_date=date(2027, 1, 31),
            capacity=25,
        )

        demo_enrollment = get_or_create_enrollment(
            db,
            "ENR-DEMO-001",
            student_id=student.id,
            batch_id=python_batch.id,
            admission_date=date(2026, 9, 25),
            status="active",
        )
        aarav_enrollment = get_or_create_enrollment(
            db,
            "ENR-DEMO-002",
            student_id=second_student.id,
            batch_id=python_batch.id,
            admission_date=date(2026, 9, 26),
            status="active",
        )
        diya_enrollment = get_or_create_enrollment(
            db,
            "ENR-DEMO-003",
            student_id=third_student.id,
            batch_id=data_batch.id,
            admission_date=date(2026, 9, 27),
            status="active",
        )

        fee_data = [
            (demo_enrollment, Decimal("60000"), Decimal("10000"), "FEE-DEMO-001", Decimal("25000")),
            (aarav_enrollment, Decimal("60000"), Decimal("0"), "FEE-DEMO-002", Decimal("20000")),
            (diya_enrollment, Decimal("45000"), Decimal("5000"), "FEE-DEMO-003", Decimal("0")),
        ]
        for enrollment, total, discount, receipt, first_payment in fee_data:
            plan = db.scalar(select(FeePlan).where(FeePlan.enrollment_id == enrollment.id))
            if plan is None:
                plan = FeePlan(
                    enrollment_id=enrollment.id,
                    total_amount=total,
                    discount_amount=discount,
                    scholarship_amount=Decimal("0"),
                )
                db.add(plan)
                db.flush()
            net_total = total - discount
            installments = list(
                db.scalars(
                    select(FeeInstallment)
                    .where(FeeInstallment.fee_plan_id == plan.id)
                    .order_by(FeeInstallment.installment_number)
                ).all()
            )
            if not installments:
                installments = [
                    FeeInstallment(
                        fee_plan_id=plan.id,
                        installment_number=1,
                        amount=net_total / 2,
                        due_date=date(2026, 10, 10),
                    ),
                    FeeInstallment(
                        fee_plan_id=plan.id,
                        installment_number=2,
                        amount=net_total / 2,
                        due_date=date(2026, 12, 10),
                    ),
                ]
                db.add_all(installments)
                db.flush()
            else:
                installments[0].amount = net_total / 2
                if len(installments) > 1:
                    installments[1].amount = net_total / 2
            first = installments[0]
            if first_payment and db.scalar(
                select(Payment).where(Payment.receipt_number == receipt)
            ) is None:
                db.add(
                    Payment(
                        receipt_number=receipt,
                        installment_id=first.id,
                        amount=first_payment,
                        payment_method="upi",
                        payment_date=date(2026, 10, 5),
                        reference=f"UPI-{receipt}",
                    )
                )
                db.flush()
            for installment in installments:
                paid = sum(
                    (payment.amount for payment in installment.payments),
                    Decimal("0"),
                )
                if paid >= installment.amount:
                    installment.status = "paid"
                elif paid > 0:
                    installment.status = "partial"
                else:
                    installment.status = "pending"

        attendance_data = [
            (demo_enrollment, "present", "Demo attendance record"),
            (aarav_enrollment, "late", "Joined after the first session"),
            (diya_enrollment, "absent", "Medical leave"),
        ]
        for enrollment, status, remarks in attendance_data:
            existing = db.scalar(
                select(Attendance).where(
                    Attendance.enrollment_id == enrollment.id,
                    Attendance.attendance_date == TODAY,
                )
            )
            if existing is None:
                db.add(
                    Attendance(
                        enrollment_id=enrollment.id,
                        attendance_date=TODAY,
                        status=status,
                        remarks=remarks,
                        marked_by_id=faculty.id,
                    )
                )

        examination = db.scalar(
            select(Examination).where(
                Examination.name == "October 2026 Assessment",
                Examination.batch_id == python_batch.id,
            )
        )
        if examination is None:
            examination = Examination(
                name="October 2026 Assessment",
                batch_id=python_batch.id,
                exam_date=date(2026, 10, 20),
                is_published=True,
            )
            db.add(examination)
            db.flush()
            subjects = [
                ExamSubject(
                    examination_id=examination.id,
                    name="Python Programming",
                    max_marks=100,
                    pass_marks=40,
                ),
                ExamSubject(
                    examination_id=examination.id,
                    name="Database Fundamentals",
                    max_marks=100,
                    pass_marks=40,
                ),
            ]
            db.add_all(subjects)
            db.flush()
            db.add_all(
                [
                    ExamMark(
                        exam_subject_id=subjects[0].id,
                        enrollment_id=demo_enrollment.id,
                        marks_obtained=88,
                        grade="A",
                        remarks="Strong practical work",
                    ),
                    ExamMark(
                        exam_subject_id=subjects[1].id,
                        enrollment_id=demo_enrollment.id,
                        marks_obtained=82,
                        grade="A",
                        remarks="Good understanding",
                    ),
                    ExamMark(
                        exam_subject_id=subjects[0].id,
                        enrollment_id=aarav_enrollment.id,
                        marks_obtained=68,
                        grade="B",
                        remarks="Keep practicing",
                    ),
                    ExamMark(
                        exam_subject_id=subjects[1].id,
                        enrollment_id=aarav_enrollment.id,
                        marks_obtained=72,
                        grade="B",
                        remarks="Good progress",
                    ),
                ]
            )

        certificate = db.scalar(
            select(Certificate).where(
                Certificate.enrollment_id == demo_enrollment.id,
                Certificate.document_type == "certificate",
            )
        )
        if certificate is None:
            certificate = Certificate(
                certificate_number="CERT-DEMO-001",
                verification_code=sha256(b"CERT-DEMO-001").hexdigest()[:24].upper(),
                enrollment_id=demo_enrollment.id,
                document_type="certificate",
                issue_date=TODAY,
                grade="A",
                percentage=85.0,
                digital_signature="Demo Director",
                is_valid=True,
            )
            db.add(certificate)

        if db.scalar(
            select(Responsibility).where(
                Responsibility.title == "October student follow-up",
                Responsibility.assigned_to_id == counsellor.id,
            )
        ) is None:
            db.add(
                Responsibility(
                    title="October student follow-up",
                    department="Counselling",
                    description="Follow up with students on attendance and progress.",
                    assigned_to_id=counsellor.id,
                    branch_id=branch.id,
                    due_date=date(2026, 10, 31),
                    status="assigned",
                    created_by_id=users["demo.superadmin@nictdemo.com"].id,
                )
            )
        if db.scalar(
            select(PerformanceReview).where(
                PerformanceReview.user_id == staff.id,
                PerformanceReview.review_month == date(2026, 10, 1),
            )
        ) is None:
            db.add(
                PerformanceReview(
                    user_id=staff.id,
                    review_month=date(2026, 10, 1),
                    follow_ups_completed=12,
                    admissions_handled=8,
                    rating=4,
                    notes="Consistent operational support.",
                    reviewed_by_id=users["demo.superadmin@nictdemo.com"].id,
                )
            )

        # A few pipeline examples so the CRM screen is not empty on a fresh demo.
        get_or_create_enquiry(
            db,
            "ENQ-DEMO-001",
            full_name="Rohit Desai",
            email="rohit.desai@example.com",
            phone="+91 98765 41101",
            branch_id=branch.id,
            course_id=python_course.id,
            source="whatsapp",
            status="new_lead",
            notes="Asked about the next Python weekend batch.",
            follow_up_date=TODAY,
            counsellor_id=counsellor.id,
        )
        get_or_create_enquiry(
            db,
            "ENQ-DEMO-002",
            full_name="Sneha Patel",
            email="sneha.patel@example.com",
            phone="+91 98765 41102",
            branch_id=branch.id,
            course_id=data_course.id,
            source="referral",
            status="demo",
            notes="Attended a demo class; comparing timings with work.",
            follow_up_date=date(2026, 10, 28),
            counsellor_id=counsellor.id,
        )
        get_or_create_enquiry(
            db,
            "ENQ-DEMO-003",
            full_name="Vikram Singh",
            email="vikram.singh@example.com",
            phone="+91 98765 41103",
            branch_id=branch.id,
            course_id=python_course.id,
            source="walk_in",
            status="admitted",
            notes="Converted after counselling.",
            follow_up_date=None,
            counsellor_id=counsellor.id,
            student_id=second_student.id,
            converted_at=datetime(2026, 9, 26, 10, 30),
        )

        db.commit()
    print("Demo institute data is ready.")


if __name__ == "__main__":
    seed_demo_data()
