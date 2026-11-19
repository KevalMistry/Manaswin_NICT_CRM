from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    student_id: int
    batch_id: int
    admission_date: date


class EnrollmentStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(active|completed|cancelled)$")


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enrollment_code: str
    student_id: int
    batch_id: int
    admission_date: date
    status: str
    course_end_date: date | None = None
    days_remaining: int | None = None
    created_at: datetime
