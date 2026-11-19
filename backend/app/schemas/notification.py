from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


NotificationCategory = Literal["fee_reminder", "course_completion"]
NotificationChannel = Literal["email", "whatsapp"]


class NotificationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    template_key: str | None = None
    channel: str
    status: str
    recipient: str | None
    subject: str | None
    message: str
    error: str | None
    branch_id: int | None
    student_id: int | None
    student_name: str | None = None
    enrollment_id: int | None
    triggered_by_id: int | None
    created_at: datetime


class NotificationPreviewItem(BaseModel):
    category: str
    channel: str
    recipient: str | None
    student_id: int
    student_name: str
    enrollment_id: int | None
    branch_id: int | None
    subject: str | None
    status: str
    detail: str | None = None


class NotificationPreviewResponse(BaseModel):
    categories: list[str]
    channels: list[str]
    items: list[NotificationPreviewItem]
    total: int
    ready: int
    skipped: int


class NotificationRunRequest(BaseModel):
    categories: list[NotificationCategory] = Field(
        default_factory=lambda: ["fee_reminder", "course_completion"]
    )
    channels: list[NotificationChannel] = Field(default_factory=lambda: ["email"])
    days_ahead: int = Field(default=7, ge=0, le=90)
    dry_run: bool = True
    # A non-dry run can reach real students, so the caller must opt in
    # explicitly. This prevents an accidental click (or a test script) from
    # messaging real contacts when SMTP/WhatsApp happen to be configured.
    confirm_live: bool = False


class NotificationRunResponse(BaseModel):
    dry_run: bool
    categories: list[str]
    channels: list[str]
    sent: int
    skipped: int
    failed: int
    dry_run_count: int
    items: list[NotificationPreviewItem]


class NotificationSettingsResponse(BaseModel):
    email_configured: bool
    whatsapp_configured: bool
    automation_enabled: bool
    automation_dry_run: bool
    automation_channels: list[str]
    automation_interval_hours: float
    automation_auto_certificates: bool
    live_sends_require_confirmation: bool = True
