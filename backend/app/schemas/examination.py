from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExamSubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    max_marks: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    pass_marks: Decimal = Field(gt=0, max_digits=8, decimal_places=2)

    @model_validator(mode="after")
    def validate_marks(self) -> "ExamSubjectCreate":
        if self.pass_marks > self.max_marks:
            raise ValueError("pass_marks cannot exceed max_marks")
        return self


class ExamSubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    max_marks: Decimal
    pass_marks: Decimal


class ExaminationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    batch_id: int
    exam_date: date
    subjects: list[ExamSubjectCreate] = Field(min_length=1, max_length=50)


class ExaminationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    batch_id: int
    exam_date: date
    is_published: bool
    subjects: list[ExamSubjectResponse] = []


class ExamMarkCreate(BaseModel):
    exam_subject_id: int
    enrollment_id: int
    marks_obtained: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    remarks: str | None = Field(default=None, max_length=255)


class ExamMarkUpdate(BaseModel):
    marks_obtained: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    remarks: str | None = Field(default=None, max_length=255)


class ExamMarkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_subject_id: int
    enrollment_id: int
    marks_obtained: Decimal
    grade: str
    remarks: str | None
