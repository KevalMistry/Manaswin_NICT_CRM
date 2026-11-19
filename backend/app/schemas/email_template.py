from datetime import datetime

from pydantic import BaseModel, Field


class EmailTemplateResponse(BaseModel):
    template_key: str
    name: str
    branch_id: int | None
    branch_name: str | None = None
    subject_template: str
    html_body: str
    text_body: str | None
    is_active: bool
    source: str
    editable: bool
    can_reset: bool = False
    variables: list[str]
    required_variables: list[str]
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class EmailTemplateUpdate(BaseModel):
    branch_id: int | None = None
    subject_template: str = Field(min_length=2, max_length=255)
    html_body: str = Field(min_length=20)
    text_body: str | None = None
    is_active: bool = True


class EmailTemplatePreviewRequest(BaseModel):
    branch_id: int | None = None
    subject_template: str = Field(min_length=2, max_length=255)
    html_body: str = Field(min_length=20)
    text_body: str | None = None


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    html: str
    text: str
    warnings: list[str] = []
