from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    gstin: str | None = Field(default=None, max_length=20)
    upi_id: str | None = Field(
        default=None,
        max_length=120,
        pattern=r"^[A-Za-z0-9._-]{2,}@[A-Za-z][A-Za-z0-9]{1,}$",
    )
    upi_payee_name: str | None = Field(default=None, max_length=120)
    upi_qr_code_url: str | None = Field(default=None, max_length=255)
    certificate_title: str | None = Field(default=None, max_length=180)
    marksheet_title: str | None = Field(default=None, max_length=180)
    certificate_primary_color: str = Field(default="#172a43", pattern=r"^#[0-9A-Fa-f]{6}$")
    certificate_accent_color: str = Field(default="#c19a3d", pattern=r"^#[0-9A-Fa-f]{6}$")
    certificate_template: str | None = Field(default=None, max_length=12000)
    marksheet_template: str | None = Field(default=None, max_length=12000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geofence_radius_meters: int = Field(default=150, ge=25, le=5000)
    office_network: str | None = Field(default=None, max_length=255)


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    gstin: str | None = Field(default=None, max_length=20)
    upi_id: str | None = Field(
        default=None,
        max_length=120,
        pattern=r"^[A-Za-z0-9._-]{2,}@[A-Za-z][A-Za-z0-9]{1,}$",
    )
    upi_payee_name: str | None = Field(default=None, max_length=120)
    upi_qr_code_url: str | None = Field(default=None, max_length=255)
    certificate_title: str | None = Field(default=None, max_length=180)
    marksheet_title: str | None = Field(default=None, max_length=180)
    certificate_primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    certificate_accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    certificate_template: str | None = Field(default=None, max_length=12000)
    marksheet_template: str | None = Field(default=None, max_length=12000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geofence_radius_meters: int | None = Field(default=None, ge=25, le=5000)
    office_network: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: str | None
    phone: str | None
    email: EmailStr | None
    gstin: str | None
    upi_id: str | None
    upi_payee_name: str | None
    upi_qr_code_url: str | None
    certificate_title: str | None
    marksheet_title: str | None
    certificate_primary_color: str
    certificate_accent_color: str
    certificate_template: str | None
    marksheet_template: str | None
    latitude: float | None
    longitude: float | None
    geofence_radius_meters: int
    office_network: str | None
    is_active: bool
    created_at: datetime
