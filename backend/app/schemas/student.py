from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    branch_id: int
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    aadhaar_number: str | None = Field(default=None, max_length=20)
    pan_number: str | None = Field(default=None, max_length=20)
    parent_name: str | None = Field(default=None, max_length=150)
    parent_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    qualification: str | None = Field(default=None, max_length=255)
    skill_level: str | None = Field(default=None, max_length=50)
    photo_url: str | None = Field(default=None, max_length=500)


class StudentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    branch_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    aadhaar_number: str | None = Field(default=None, max_length=20)
    pan_number: str | None = Field(default=None, max_length=20)
    parent_name: str | None = Field(default=None, max_length=150)
    parent_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    qualification: str | None = Field(default=None, max_length=255)
    skill_level: str | None = Field(default=None, max_length=50)
    photo_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class StudentAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class StudentAccountResponse(BaseModel):
    student_id: int
    user_id: int
    email: EmailStr


class StudentDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    document_type: str
    title: str
    file_name: str
    file_url: str
    content_type: str | None
    file_size: int
    uploaded_by_id: int | None
    uploaded_at: datetime


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_code: str
    roll_number: str | None
    full_name: str
    branch_id: int
    email: EmailStr | None
    phone: str | None
    date_of_birth: date | None
    gender: str | None
    aadhaar_number: str | None
    pan_number: str | None
    parent_name: str | None
    parent_phone: str | None
    address: str | None
    qualification: str | None
    skill_level: str | None
    photo_url: str | None
    is_active: bool
    created_at: datetime
    user_id: int | None
