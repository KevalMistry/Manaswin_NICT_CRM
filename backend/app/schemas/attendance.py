from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AttendanceCreate(BaseModel):
    enrollment_id: int
    attendance_date: date
    status: str = Field(pattern=r"^(present|absent|late|excused)$")
    remarks: str | None = Field(default=None, max_length=255)


class AttendanceUpdate(BaseModel):
    status: str = Field(pattern=r"^(present|absent|late|excused)$")
    remarks: str | None = Field(default=None, max_length=255)


class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enrollment_id: int
    attendance_date: date
    status: str
    remarks: str | None
    marked_by_id: int | None
    created_at: datetime


class AttendanceSessionCreate(BaseModel):
    batch_id: int
    attendance_date: date
    expires_in_minutes: int = Field(default=10, ge=1, le=30)


class AttendanceSessionResponse(BaseModel):
    session_id: int
    batch_id: int
    attendance_date: date
    expires_at: datetime
    token: str


class QRAttendanceCreate(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class StaffAttendanceCreate(BaseModel):
    user_id: int | None = None
    attendance_date: date
    status: str = Field(pattern=r"^(present|absent|late|leave|half_day)$")
    check_in: datetime | None = None
    check_out: datetime | None = None
    remarks: str | None = Field(default=None, max_length=255)


class StaffSelfCheckInRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=10000)


class StaffAttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    attendance_date: date
    status: str
    check_in: datetime | None
    check_out: datetime | None
    remarks: str | None
    latitude: float | None = None
    longitude: float | None = None
    distance_meters: float | None = None
    location_status: str | None = None
    ip_address: str | None = None
    marked_by_id: int | None
    created_at: datetime
    user_name: str | None = None
    user_role: str | None = None
    branch_id: int | None = None
    branch_name: str | None = None


class StaffAttendancePerson(BaseModel):
    id: int
    full_name: str
    role_name: str
    branch_id: int | None
    branch_name: str | None
    phone: str | None = None


class StaffAttendanceSummaryRow(BaseModel):
    user_id: int
    user_name: str
    role_name: str
    branch_name: str | None
    present: int
    absent: int
    late: int
    leave: int
    half_day: int
    recorded_days: int
    attendance_rate: float
