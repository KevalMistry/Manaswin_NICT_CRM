from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = None
    duration_months: int = Field(ge=1, le=120)
    fee_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    registration_fee: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=2
    )
    application_fee: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=2
    )
    exam_fee: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=2
    )


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    description: str | None = None
    duration_months: int | None = Field(default=None, ge=1, le=120)
    fee_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    registration_fee: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    application_fee: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    exam_fee: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    is_active: bool | None = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    description: str | None
    duration_months: int
    fee_amount: Decimal | None
    registration_fee: Decimal
    application_fee: Decimal
    exam_fee: Decimal
    is_active: bool
    created_at: datetime
