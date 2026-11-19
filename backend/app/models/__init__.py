from app.models.admission import (
    AdmissionApplication,
    AdmissionDocument,
    AdmissionPayment,
)
from app.models.attendance import Attendance, AttendanceSession
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.enquiry import Enquiry
from app.models.examination import ExamMark, ExamSubject, Examination
from app.models.fee import (
    EmailTemplate,
    FeeInstallment,
    FeePlan,
    Payment,
    PaymentClaim,
)
from app.models.finance import BankAccount, Expense, FranchiseProfile, RoyaltyPayment
from app.models.lms import (
    Assignment,
    AssignmentSubmission,
    CourseModule,
    Lesson,
    LessonProgress,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
)
from app.models.online_exam import (
    BankQuestion,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    OnlineExam,
    QuestionBank,
)
from app.models.notification import NotificationLog
from app.models.parent import ParentStudentLink
from app.models.placement import (
    Company,
    JobOpening,
    PlacementApplication,
    job_opening_courses,
)
from app.models.role import Role
from app.models.responsibility import PerformanceReview, Responsibility
from app.models.staff_attendance import StaffAttendance
from app.models.student import Student
from app.models.student_document import StudentDocument
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.models.permission import RoleModulePermission

__all__ = [
    "AdmissionApplication", "AdmissionDocument", "AdmissionPayment",
    "Attendance", "AttendanceSession", "AuditLog", "Batch", "Branch", "Certificate", "Course", "Enrollment", "Enquiry", "ExamMark",
    "ExamSubject", "Examination", "EmailTemplate", "FeeInstallment", "FeePlan", "Payment", "PaymentClaim",
    "BankAccount", "Expense", "FranchiseProfile", "RoyaltyPayment",
    "Assignment", "AssignmentSubmission", "CourseModule", "Lesson", "LessonProgress",
    "Quiz", "QuizAnswer", "QuizAttempt", "QuizQuestion",
    "BankQuestion", "ExamAnswer", "ExamAttempt", "ExamQuestion", "OnlineExam", "QuestionBank",
    "NotificationLog",
    "ParentStudentLink",
    "Company", "JobOpening", "PlacementApplication", "job_opening_courses",
    "Role", "StaffAttendance", "Student", "StudentDocument", "User", "Responsibility", "PerformanceReview",
    "PasswordResetToken", "RoleModulePermission",
]
