from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.enrollment import EnrollmentResponse
from app.schemas.student import StudentResponse


ENQUIRY_STATUSES = ("new_lead", "follow_up", "demo", "counselling", "admitted", "lost")
ENQUIRY_SOURCES = (
    "walk_in",
    "online",
    "website",
    "whatsapp",
    "facebook",
    "google_ads",
    "referral",
    "other",
)
EDITABLE_STATUSES = ("new_lead", "follow_up", "demo", "counselling", "lost")


class EnquiryCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    branch_id: int
    course_id: int | None = None
    source: str = Field(default="walk_in", pattern=r"^(" + "|".join(ENQUIRY_SOURCES) + r")$")
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    counsellor_id: int | None = None


class EnquiryUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    branch_id: int | None = None
    course_id: int | None = None
    source: str | None = Field(
        default=None, pattern=r"^(" + "|".join(ENQUIRY_SOURCES) + r")$"
    )
    status: str | None = Field(
        default=None, pattern=r"^(" + "|".join(EDITABLE_STATUSES) + r")$"
    )
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    counsellor_id: int | None = None


class EnquiryConvertRequest(BaseModel):
    batch_id: int
    admission_date: date
    # Link an existing student instead of creating a new one from the enquiry.
    student_id: int | None = None


class EnquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enquiry_code: str
    full_name: str
    email: EmailStr | None
    phone: str | None
    branch_id: int
    course_id: int | None
    source: str
    status: str
    notes: str | None
    follow_up_date: date | None
    counsellor_id: int | None
    student_id: int | None
    converted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EnquiryConvertResponse(BaseModel):
    enquiry: EnquiryResponse
    student: StudentResponse
    enrollment: EnrollmentResponse
