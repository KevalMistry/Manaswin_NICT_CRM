from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CertificateCreate(BaseModel):
    enrollment_id: int
    document_type: str = Field(pattern=r"^(certificate|marksheet)$")
    digital_signature: str | None = Field(default=None, max_length=255)
    # Super Admin override for genuine fast-track cases. All other roles must
    # wait until the course end date.
    allow_early: bool = False


class CertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    certificate_number: str
    verification_code: str
    enrollment_id: int
    document_type: str
    issue_date: date
    grade: str | None
    percentage: float | None
    digital_signature: str | None
    is_valid: bool
    created_at: datetime


class CertificateVerificationResponse(BaseModel):
    valid: bool
    certificate_number: str
    document_type: str
    issue_date: date
    student_name: str
    student_code: str
    course_name: str
    branch_name: str
    grade: str | None
    percentage: float | None


class AttendanceEligibility(BaseModel):
    recorded_days: int
    present_days: int
    late_days: int
    excused_days: int
    attended_days: int
    percentage: float
    minimum_percentage: float
    met: bool
    note: str | None = None


class FeeEligibility(BaseModel):
    has_fee_plan: bool
    total_fee: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    met: bool


class ExamEligibility(BaseModel):
    published_subjects: int
    marked_subjects: int
    all_marks_recorded: bool
    grade: str | None
    passed: bool
    met: bool


class AssignmentEligibility(BaseModel):
    tracked: bool
    met: bool
    note: str


class OnlineExamEligibility(BaseModel):
    tracked: bool
    total_exams: int
    passed_exams: int
    met: bool
    note: str


class CourseTimingEligibility(BaseModel):
    course_duration_months: int
    course_end_date: date | None
    days_remaining: int | None
    completed: bool
    met: bool
    note: str | None = None


class CertificateEligibilityResponse(BaseModel):
    enrollment_id: int
    enrollment_status: str
    document_type: str
    student_name: str
    student_code: str
    course_name: str
    course_timing: CourseTimingEligibility
    attendance: AttendanceEligibility
    fees: FeeEligibility
    exams: ExamEligibility
    assignments: AssignmentEligibility
    online_exams: OnlineExamEligibility
    eligible: bool
    blockers: list[str]


class CertificateAutoIssueRequest(BaseModel):
    document_type: str = Field(default="certificate", pattern=r"^(certificate|marksheet)$")
    dry_run: bool = False
    digital_signature: str | None = Field(default=None, max_length=255)


class CertificateAutoIssueItem(BaseModel):
    enrollment_id: int
    student_name: str
    course_name: str
    course_end_date: date | None
    action: str
    detail: str | None = None


class CertificateAutoIssueResponse(BaseModel):
    scanned: int
    completed_enrollments: int
    issued: int
    skipped: int
    dry_run: bool
    items: list[CertificateAutoIssueItem]
