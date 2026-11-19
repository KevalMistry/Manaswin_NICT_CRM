from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


APPLICATION_STATUSES = (
    "applied",
    "shortlisted",
    "interview_scheduled",
    "selected",
    "offer_released",
    "joined",
    "rejected",
    "withdrawn",
)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------
class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None
    is_active: bool = True


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None
    is_active: bool | None = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    industry: str | None
    website: str | None
    location: str | None
    contact_person: str | None
    contact_email: str | None
    contact_phone: str | None
    notes: str | None
    is_active: bool
    openings_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Job openings
# ---------------------------------------------------------------------------
class JobOpeningCreate(BaseModel):
    company_id: int
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    location: str | None = Field(default=None, max_length=150)
    employment_type: str = Field(default="Full-time", max_length=30)
    work_mode: str = Field(default="On-site", max_length=20)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    vacancies: int = Field(default=1, ge=1, le=1000)
    last_date: date | None = None
    status: str = Field(default="open", pattern="^(open|closed)$")
    branch_id: int | None = None
    course_ids: list[int] = Field(default_factory=list)


class JobOpeningUpdate(BaseModel):
    company_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    location: str | None = Field(default=None, max_length=150)
    employment_type: str | None = Field(default=None, max_length=30)
    work_mode: str | None = Field(default=None, max_length=20)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    vacancies: int | None = Field(default=None, ge=1, le=1000)
    last_date: date | None = None
    status: str | None = Field(default=None, pattern="^(open|closed)$")
    branch_id: int | None = None
    course_ids: list[int] | None = None


class JobOpeningResponse(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    description: str | None
    location: str | None
    employment_type: str
    work_mode: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    vacancies: int
    last_date: date | None
    status: str
    branch_id: int | None
    branch_name: str | None
    course_ids: list[int]
    course_names: list[str]
    applications_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Applications (placement office)
# ---------------------------------------------------------------------------
class ApplicationCreate(BaseModel):
    job_opening_id: int
    student_id: int
    status: str = Field(default="applied", pattern="^(" + "|".join(APPLICATION_STATUSES) + ")$")
    resume_url: str | None = Field(default=None, max_length=500)
    cover_note: str | None = None


class ApplicationUpdate(BaseModel):
    status: str | None = Field(
        default=None, pattern="^(" + "|".join(APPLICATION_STATUSES) + ")$"
    )
    resume_url: str | None = Field(default=None, max_length=500)
    cover_note: str | None = None
    interview_date: datetime | None = None
    interview_mode: str | None = Field(default=None, max_length=30)
    interview_location: str | None = Field(default=None, max_length=255)
    feedback: str | None = None
    offer_salary: Decimal | None = Field(default=None, ge=0)
    offer_date: date | None = None
    joining_date: date | None = None
    offer_letter_url: str | None = Field(default=None, max_length=500)


class ApplicationResponse(BaseModel):
    id: int
    job_opening_id: int
    opening_title: str
    company_name: str
    student_id: int
    student_name: str
    student_code: str
    branch_id: int
    branch_name: str
    course_names: list[str]
    status: str
    source: str
    resume_url: str | None
    cover_note: str | None
    interview_date: datetime | None
    interview_mode: str | None
    interview_location: str | None
    feedback: str | None
    offer_salary: Decimal | None
    offer_date: date | None
    joining_date: date | None
    offer_letter_url: str | None
    applied_at: datetime
    updated_at: datetime


class PlacementSummary(BaseModel):
    companies: int
    open_openings: int
    total_applications: int
    by_status: dict[str, int]
    offers_released: int
    joined: int


# ---------------------------------------------------------------------------
# Student placement portal
# ---------------------------------------------------------------------------
class OpportunityResponse(BaseModel):
    id: int
    company_name: str
    title: str
    description: str | None
    location: str | None
    employment_type: str
    work_mode: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    vacancies: int
    last_date: date | None
    course_names: list[str]
    application_id: int | None
    application_status: str | None


class StudentApplicationResponse(BaseModel):
    id: int
    job_opening_id: int
    opening_title: str
    company_name: str
    status: str
    interview_date: datetime | None
    interview_mode: str | None
    interview_location: str | None
    feedback: str | None
    offer_salary: Decimal | None
    offer_date: date | None
    joining_date: date | None
    offer_letter_url: str | None
    applied_at: datetime


class StudentApplyRequest(BaseModel):
    resume_url: str | None = Field(default=None, max_length=500)
    cover_note: str | None = None
