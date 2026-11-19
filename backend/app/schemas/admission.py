from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdmissionCatalogCourse(BaseModel):
    id: int
    name: str
    code: str
    duration_months: int
    fee_amount: Decimal | None
    registration_fee: Decimal


class AdmissionCatalogBranch(BaseModel):
    id: int
    name: str
    code: str
    address: str | None
    phone: str | None
    email: str | None
    gstin: str | None


class AdmissionCatalogResponse(BaseModel):
    branches: list[AdmissionCatalogBranch]
    courses: list[AdmissionCatalogCourse]
    payment_provider: str
    payment_currency: str
    gst_rate_percent: float


class PublicAdmissionCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str = Field(min_length=6, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    parent_name: str | None = Field(default=None, max_length=150)
    parent_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    qualification: str | None = Field(default=None, max_length=255)
    branch_id: int
    course_id: int
    notes: str | None = Field(default=None, max_length=1000)


class PublicAdmissionCreated(BaseModel):
    application_id: int
    application_code: str
    upload_token: str
    status: str
    payment_status: str
    registration_fee: Decimal
    course_name: str
    branch_name: str
    message: str


class PublicAdmissionDocument(BaseModel):
    id: int
    document_type: str
    title: str
    file_name: str
    content_type: str | None
    file_size: int
    uploaded_at: datetime
    download_url: str


class PublicAdmissionPayment(BaseModel):
    amount: Decimal
    status: str
    payment_method: str
    provider: str
    reference: str | None
    invoice_number: str | None
    paid_at: datetime | None
    created_at: datetime


class PublicAdmissionStatus(BaseModel):
    application_code: str
    full_name: str
    email: str | None
    phone: str
    branch_name: str
    course_name: str
    status: str
    payment_status: str
    registration_fee: Decimal
    total_paid: Decimal
    documents: list[PublicAdmissionDocument]
    payments: list[PublicAdmissionPayment]
    student_code: str | None
    roll_number: str | None
    enrollment_code: str | None
    rejection_reason: str | None
    created_at: datetime


class PublicPaymentIntentResponse(BaseModel):
    application_code: str
    provider: str
    status: str
    payment_status: str
    amount: Decimal
    currency: str
    order_id: str | None
    key_id: str | None
    instructions: str


class PublicPaymentVerifyRequest(BaseModel):
    order_id: str = Field(min_length=4, max_length=100)
    payment_id: str = Field(min_length=4, max_length=100)
    signature: str = Field(min_length=10, max_length=200)


class PublicPaymentVerifyResponse(BaseModel):
    application_code: str
    payment_status: str
    invoice_number: str | None
    message: str


class AdmissionDocumentResponse(BaseModel):
    id: int
    document_type: str
    title: str
    file_name: str
    content_type: str | None
    file_size: int
    uploaded_at: datetime
    download_url: str


class AdmissionPaymentResponse(BaseModel):
    id: int
    invoice_number: str | None
    amount: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    payment_method: str
    provider: str
    status: str
    reference: str | None
    provider_order_id: str | None
    provider_payment_id: str | None
    paid_at: datetime | None
    recorded_by: str | None
    created_at: datetime


class AdmissionResponse(BaseModel):
    id: int
    application_code: str
    full_name: str
    email: str | None
    phone: str
    date_of_birth: date | None
    gender: str | None
    parent_name: str | None
    parent_phone: str | None
    address: str | None
    qualification: str | None
    notes: str | None
    branch_id: int
    branch_name: str
    course_id: int
    course_name: str
    batch_id: int | None
    batch_name: str | None
    status: str
    payment_status: str
    registration_fee: Decimal
    total_paid: Decimal
    documents_count: int
    source: str
    review_notes: str | None
    rejection_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    student_id: int | None
    student_code: str | None
    roll_number: str | None
    enrollment_id: int | None
    enrollment_code: str | None
    created_at: datetime
    updated_at: datetime


class AdmissionDetailResponse(AdmissionResponse):
    documents: list[AdmissionDocumentResponse]
    payments: list[AdmissionPaymentResponse]


class AdmissionStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(submitted|under_review|rejected|withdrawn)$")
    notes: str | None = Field(default=None, max_length=1000)
    rejection_reason: str | None = Field(default=None, max_length=1000)


class AdmissionApproveRequest(BaseModel):
    batch_id: int
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=2
    )
    notes: str | None = Field(default=None, max_length=1000)
    override_unpaid_fee: bool = False


class AdmissionApproveResponse(BaseModel):
    application: AdmissionDetailResponse
    student_id: int
    student_code: str
    roll_number: str
    enrollment_id: int
    enrollment_code: str
    fee_plan_id: int | None


class AdmissionRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdmissionPaymentCreate(BaseModel):
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    payment_method: str = Field(default="cash", max_length=30)
    payment_date: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class AdmissionInvoiceResponse(BaseModel):
    invoice_number: str
    invoice_date: date
    application_code: str
    applicant_name: str
    student_code: str | None
    roll_number: str | None
    course_name: str
    branch_name: str
    branch_address: str | None
    branch_phone: str | None
    branch_email: str | None
    branch_gstin: str | None
    amount: Decimal
    taxable_amount: Decimal
    gst_rate_percent: float
    gst_amount: Decimal
    payment_method: str
    reference: str | None
    status: str
    paid_at: datetime | None


class AdmissionStatsResponse(BaseModel):
    total: int
    submitted: int
    under_review: int
    enrolled: int
    rejected: int
    withdrawn: int
    unpaid: int
    pending_payment: int
    paid: int
    fees_collected: Decimal
