from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class StudentPortalInstallment(BaseModel):
    id: int
    installment_number: int
    amount: Decimal
    due_date: date
    status: str
    paid: Decimal
    pending_claim_amount: Decimal
    claimable_amount: Decimal


class StudentPortalPayment(BaseModel):
    payment_id: int
    receipt_number: str
    installment_number: int
    amount: Decimal
    payment_method: str
    payment_date: date
    reference: str | None


class StudentPortalClaim(BaseModel):
    id: int
    installment_id: int
    installment_number: int
    amount: Decimal
    upi_reference: str
    paid_on: date
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None
    rejection_code: str | None
    rejection_reason: str | None
    staff_note: str | None
    payment_id: int | None
    receipt_number: str | None


class StudentPortalEnrollment(BaseModel):
    enrollment_id: int
    enrollment_code: str
    batch_name: str
    course_name: str
    status: str
    branch_id: int
    branch_name: str
    upi_id: str | None
    upi_payee_name: str | None
    upi_qr_code_url: str | None
    total_fee: Decimal
    total_paid: Decimal
    balance: Decimal
    installments: list[StudentPortalInstallment]
    payments: list[StudentPortalPayment]
    claims: list[StudentPortalClaim]


class StudentPortalAttendance(BaseModel):
    enrollment_code: str
    total: int
    present: int
    late: int
    absent: int
    percentage: float


class StudentPortalResult(BaseModel):
    examination: str
    exam_date: date
    subject: str
    marks_obtained: Decimal
    maximum_marks: Decimal
    grade: str


class StudentPortalCertificate(BaseModel):
    id: int
    certificate_number: str
    verification_code: str
    document_type: str
    issue_date: date
    grade: str | None
    percentage: float | None
    is_valid: bool


class StudentPortalResponse(BaseModel):
    student_code: str
    full_name: str
    email: str | None
    phone: str | None
    enrollments: list[StudentPortalEnrollment]
    attendance: list[StudentPortalAttendance]
    results: list[StudentPortalResult]
    certificates: list[StudentPortalCertificate]
