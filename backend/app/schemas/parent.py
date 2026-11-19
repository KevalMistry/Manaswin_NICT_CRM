from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Admin management of parent accounts
# ---------------------------------------------------------------------------
class ParentChildLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    link_id: int
    student_id: int
    student_code: str
    student_name: str
    relationship: str
    is_primary: bool


class ParentAccountResponse(BaseModel):
    user_id: int
    full_name: str
    email: EmailStr
    phone: str | None
    branch_id: int | None
    branch_name: str | None
    is_active: bool
    created_at: datetime
    children: list[ParentChildLinkResponse]


class ParentAccountCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=30)
    branch_id: int | None = None
    student_ids: list[int] = Field(default_factory=list)
    relationship: str = Field(default="Guardian", max_length=40)


class ParentAccountUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    branch_id: int | None = None
    is_active: bool | None = None


class ParentPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class ParentLinkCreate(BaseModel):
    student_id: int
    relationship: str = Field(default="Guardian", max_length=40)


# ---------------------------------------------------------------------------
# Read-only parent portal
# ---------------------------------------------------------------------------
class ParentPortalEnrollment(BaseModel):
    enrollment_id: int
    enrollment_code: str
    course_name: str
    batch_name: str
    status: str
    admission_date: date
    course_end_date: date | None
    days_remaining: int | None
    course_completed: bool
    attendance_percentage: float
    progress_percent: float
    completed_lessons: int
    total_lessons: int
    total_fee: Decimal
    total_paid: Decimal
    balance: Decimal
    next_due_date: date | None
    fee_status: str


class ParentPortalAttendance(BaseModel):
    enrollment_code: str
    total: int
    present: int
    late: int
    absent: int
    excused: int = 0
    percentage: float


class ParentPortalResult(BaseModel):
    examination: str
    exam_date: date | None
    subject: str
    marks_obtained: Decimal
    maximum_marks: Decimal
    grade: str | None


class ParentPortalAssignment(BaseModel):
    assignment_id: int
    title: str
    course_name: str
    due_date: date | None
    status: str
    submitted_at: datetime | None
    marks_obtained: Decimal | None
    maximum_marks: Decimal
    grade: str | None
    feedback: str | None


class ParentPortalCertificate(BaseModel):
    id: int
    certificate_number: str
    verification_code: str
    document_type: str
    issue_date: date
    grade: str | None
    percentage: float | None
    is_valid: bool


class ParentPortalChild(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    photo_url: str | None
    branch_name: str
    relationship: str
    is_primary: bool
    enrollments: list[ParentPortalEnrollment]
    attendance: list[ParentPortalAttendance]
    results: list[ParentPortalResult]
    assignments: list[ParentPortalAssignment]
    certificates: list[ParentPortalCertificate]


class ParentPortalResponse(BaseModel):
    parent_name: str
    email: EmailStr
    phone: str | None
    children: list[ParentPortalChild]
