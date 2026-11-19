from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    course_id: int
    branch_id: int
    faculty_id: int | None = None
    start_date: date
    end_date: date | None = None
    capacity: int = Field(default=30, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_dates(self) -> "BatchCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class BatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    course_id: int | None = None
    branch_id: int | None = None
    faculty_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity: int | None = Field(default=None, ge=1, le=1000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "BatchUpdate":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
        return self


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    course_id: int
    branch_id: int
    faculty_id: int | None
    start_date: date
    end_date: date | None
    capacity: int
    is_active: bool
    created_at: datetime
