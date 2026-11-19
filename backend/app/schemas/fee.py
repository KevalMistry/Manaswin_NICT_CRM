from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InstallmentCreate(BaseModel):
    installment_number: int = Field(ge=1)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    due_date: date


class FeePlanCreate(BaseModel):
    enrollment_id: int
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    discount_amount: Decimal = Field(default=0, ge=0, max_digits=12, decimal_places=2)
    scholarship_amount: Decimal = Field(default=0, ge=0, max_digits=12, decimal_places=2)
    installments: list[InstallmentCreate] = Field(min_length=1, max_length=24)


class FeePlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enrollment_id: int
    total_amount: Decimal
    discount_amount: Decimal
    scholarship_amount: Decimal
    created_at: datetime


class FeeInstallmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    installment_number: int
    amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    due_date: date
    status: str


class FeeOverviewResponse(BaseModel):
    enrollment_id: int
    student_id: int
    student_name: str
    enrollment_code: str
    batch_id: int
    admission_date: date
    course_name: str
    course_fee: Decimal | None
    fee_plan: FeePlanResponse | None
    installments: list[FeeInstallmentResponse]
    total_paid: Decimal
    balance: Decimal


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method: str = Field(
        pattern=r"^(cash|bank_transfer|upi|card|cheque)$"
    )
    payment_date: date
    receipt_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    )


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: str
    installment_id: int
    amount: Decimal
    payment_method: str
    payment_date: date
    reference: str | None
    created_at: datetime


class ReceiptResponse(BaseModel):
    payment_id: int
    receipt_number: str
    student_name: str
    student_code: str
    student_roll_number: str | None = None
    student_email: str | None
    student_phone: str | None
    course_name: str
    batch_name: str
    installment_number: int
    amount: Decimal
    payment_method: str
    payment_date: date
    reference: str | None
    total_fee: Decimal
    total_paid: Decimal
    balance: Decimal
    branch_name: str
    branch_address: str | None
    branch_phone: str | None
    branch_email: str | None = None
    branch_gstin: str | None = None


class PaymentClaimCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    upi_reference: str = Field(
        min_length=6,
        max_length=60,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    paid_on: date


class PaymentClaimResponse(BaseModel):
    id: int
    installment_id: int
    installment_number: int
    student_id: int
    student_name: str
    student_code: str
    student_email: str | None
    course_name: str
    batch_name: str
    branch_id: int
    branch_name: str
    amount: Decimal
    upi_reference: str
    paid_on: date
    status: str
    submitted_at: datetime
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    rejection_code: str | None = None
    rejection_reason: str | None = None
    staff_note: str | None = None
    payment_id: int | None = None
    receipt_number: str | None = None
    receipt_email_status: str | None = None
    receipt_email_detail: str | None = None
    age_days: int = 0


class PaymentClaimRejectRequest(BaseModel):
    rejection_code: str = Field(
        default="not_received",
        pattern=r"^(not_received|amount_mismatch|invalid_reference|wrong_branch|duplicate|other)$",
    )
    rejection_reason: str = Field(min_length=3, max_length=255)
    staff_note: str | None = Field(default=None, max_length=255)


class PaymentClaimApproveRequest(BaseModel):
    staff_note: str | None = Field(default=None, max_length=255)


class EmailDeliveryResponse(BaseModel):
    sent: bool
    recipient: str | None
    message: str
    status: str = "sent"


class WhatsAppDeliveryResponse(BaseModel):
    sent: bool
    recipient: str | None
    message: str


class FeeReminderRow(BaseModel):
    installment_id: int
    enrollment_id: int
    student_id: int
    student_name: str
    student_code: str
    email: str | None
    phone: str | None
    course_name: str
    batch_name: str
    branch_id: int
    branch_name: str
    installment_number: int
    remaining_amount: Decimal
    due_date: date
    days_overdue: int
    status: str


class FeeReminderSendRequest(BaseModel):
    installment_ids: list[int] | None = None
    days_ahead: int = Field(default=7, ge=0, le=90)


class FeeReminderSendResponse(BaseModel):
    sent_count: int
    skipped_count: int
    failed_count: int
    recipients: list[str]
    skipped: list[str]
    failed: list[str]
