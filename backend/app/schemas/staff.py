from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


MANAGED_ROLES = {"Faculty", "Staff", "Counsellor"}


class ManagedUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=30)
    role_id: int
    branch_id: int


class ManagedUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_id: int | None = None
    branch_id: int | None = None
    is_active: bool | None = None


class ManagedUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role_name: str
    phone: str | None
    role_id: int
    branch_id: int | None
    is_active: bool


class ResponsibilityCreate(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    department: str = Field(min_length=2, max_length=80)
    description: str | None = None
    assigned_to_id: int
    branch_id: int
    due_date: date | None = None


class ResponsibilityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    department: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    due_date: date | None = None
    status: str | None = Field(default=None, pattern=r"^(assigned|in_progress|completed|cancelled)$")


class ResponsibilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    description: str | None
    assigned_to_id: int
    branch_id: int
    due_date: date | None
    status: str
    created_by_id: int
    created_at: datetime


class PerformanceReviewCreate(BaseModel):
    user_id: int
    review_month: date
    follow_ups_completed: int = Field(default=0, ge=0)
    admissions_handled: int = Field(default=0, ge=0)
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class PerformanceReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    review_month: date
    follow_ups_completed: int
    admissions_handled: int
    rating: int | None
    notes: str | None
    reviewed_by_id: int | None
    created_at: datetime


class PerformanceSummary(BaseModel):
    user_id: int
    assigned_responsibilities: int
    completed_responsibilities: int
    overdue_responsibilities: int
    follow_ups_completed: int
    admissions_handled: int
    latest_rating: int | None
