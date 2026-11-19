"""Editable outbound email templates.

Super Admin maintains the global defaults; Branch Admin and Staff can create a
branch override that wins over the global row for that branch only. Staff never
see or edit another branch's copy.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    require_module,
    require_roles,
)
from app.models.branch import Branch
from app.models.fee import EmailTemplate
from app.models.user import User
from app.schemas.email_template import (
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateResponse,
    EmailTemplateUpdate,
)
from app.services.email_templates import (
    DEFAULT_TEMPLATES,
    EmailTemplateError,
    format_reminder_rows,
    html_to_text,
    render_email_content,
    validate_template,
)


router = APIRouter(prefix="/api/email-templates", tags=["Email Templates"])
TemplateEditor = require_roles("Super Admin", "Branch Admin", "Staff")
NotificationsAccess = require_module("notifications")

SAMPLE_CONTEXTS: dict[str, dict[str, object]] = {
    "fee_receipt": {
        "student_name": "Aarav Sharma",
        "student_code": "NICT-2026-0042",
        "student_roll_number": "VLS-042",
        "receipt_number": "RCT-2026-4F8A2C11",
        "course_name": "Full Stack Python",
        "batch_name": "Python October 2026",
        "installment_number": 2,
        "amount": "15,000.00",
        "payment_method": "Upi",
        "payment_date": "2026-10-30",
        "reference": "412345678901",
        "total_fee": "60,000.00",
        "total_paid": "30,000.00",
        "balance": "30,000.00",
        "branch_name": "NICT Valsad",
        "branch_address": "2nd Floor, Halar Road, Valsad",
        "branch_phone": "+91 90000 00000",
        "branch_phone_suffix": " on +91 90000 00000",
        "branch_gstin": "24ABCDE1234F1Z5",
    },
    "fee_reminder": {
        "student_name": "Aarav Sharma",
        "branch_name": "NICT Valsad",
        "total_pending": "45,000.00",
        "reminder_rows": format_reminder_rows(
            [
                {
                    "course": "Full Stack Python / Python October 2026",
                    "installment": "2",
                    "amount": "15,000.00",
                    "due": "2026-10-15",
                    "status": "Overdue",
                },
                {
                    "course": "Full Stack Python / Python October 2026",
                    "installment": "3",
                    "amount": "15,000.00",
                    "due": "2026-11-15",
                    "status": "Due soon",
                },
            ]
        ),
    },
    "course_completion": {
        "student_name": "Aarav Sharma",
        "course_name": "Full Stack Python",
        "batch_name": "Python October 2026",
        "end_date": "2026-10-30",
        "branch_name": "NICT Valsad",
    },
    "password_reset": {
        "user_name": "Aarav Sharma",
        "reset_link": "https://portal.nict.example/reset?token=sample-token",
        "expires_minutes": 30,
    },
    "payment_rejected": {
        "student_name": "Aarav Sharma",
        "course_name": "Full Stack Python",
        "batch_name": "Python October 2026",
        "amount": "15,000.00",
        "upi_reference": "412345678901",
        "rejection_reason": "The UTR was not found in the branch bank statement.",
        "branch_name": "NICT Valsad",
        "branch_phone_suffix": " on +91 90000 00000",
    },
    "payment_awaiting_verification": {
        "student_name": "Aarav Sharma",
        "course_name": "Full Stack Python",
        "batch_name": "Python October 2026",
        "amount": "15,000.00",
        "upi_reference": "412345678901",
        "branch_name": "NICT Valsad",
    },
}


def _is_super_admin(user: User) -> bool:
    return user.role.name == "Super Admin"


def _resolve_scope(
    current_user: User,
    requested_branch_id: int | None,
    *,
    default_to_own_branch: bool = False,
) -> int | None:
    if _is_super_admin(current_user):
        return requested_branch_id
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not assigned to a branch",
        )
    if requested_branch_id is not None and requested_branch_id != current_user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can manage email templates for your own branch only",
        )
    if requested_branch_id is None and default_to_own_branch:
        return current_user.branch_id
    if requested_branch_id is None:
        # A non-admin must never edit the global default.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a Super Admin can edit the global email templates",
        )
    return requested_branch_id


def _load_row(
    db: DatabaseSession, key: str, branch_id: int | None
) -> EmailTemplate | None:
    query = select(EmailTemplate).where(EmailTemplate.template_key == key)
    if branch_id is None:
        query = query.where(EmailTemplate.branch_id.is_(None))
    else:
        query = query.where(EmailTemplate.branch_id == branch_id)
    return db.scalar(query)


def _effective_row(
    db: DatabaseSession, key: str, branch_id: int | None
) -> tuple[EmailTemplate | None, str]:
    if branch_id is not None:
        row = _load_row(db, key, branch_id)
        if row is not None:
            return row, "branch"
    row = _load_row(db, key, None)
    if row is not None:
        return row, "global"
    return None, "builtin"


def _template_response(
    db: DatabaseSession,
    current_user: User,
    key: str,
    branch_id: int | None,
) -> EmailTemplateResponse:
    definition = DEFAULT_TEMPLATES[key]
    row, source = _effective_row(db, key, branch_id)
    editable = _is_super_admin(current_user) or branch_id == current_user.branch_id
    if source == "global" and not _is_super_admin(current_user):
        editable = False
    branch_name = row.branch.name if row and row.branch else None
    if row is None:
        return EmailTemplateResponse(
            template_key=key,
            name=definition.name,
            branch_id=None,
            branch_name=branch_name,
            subject_template=definition.subject,
            html_body=definition.html,
            text_body=html_to_text(definition.html),
            is_active=True,
            source=source,
            editable=editable,
            can_reset=False,
            variables=list(definition.variables),
            required_variables=list(definition.required),
            updated_at=None,
            updated_by_name=None,
        )
    return EmailTemplateResponse(
        template_key=key,
        name=row.name,
        branch_id=row.branch_id,
        branch_name=branch_name,
        subject_template=row.subject_template,
        html_body=row.html_body,
        text_body=row.text_body,
        is_active=row.is_active,
        source=source,
        editable=editable,
        can_reset=source == "branch",
        variables=list(definition.variables),
        required_variables=list(definition.required),
        updated_at=row.updated_at,
        updated_by_name=row.updated_by.full_name if row.updated_by else None,
    )


@router.get(
    "",
    response_model=list[EmailTemplateResponse],
    dependencies=[Depends(NotificationsAccess)],
)
def list_email_templates(
    db: DatabaseSession,
    current_user: User = Depends(TemplateEditor),
    branch_id: int | None = Query(default=None),
) -> list[EmailTemplateResponse]:
    scope = _resolve_scope(current_user, branch_id, default_to_own_branch=True)
    return [
        _template_response(db, current_user, key, scope)
        for key in DEFAULT_TEMPLATES
    ]


@router.get(
    "/{template_key}",
    response_model=EmailTemplateResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def get_email_template(
    template_key: str,
    db: DatabaseSession,
    current_user: User = Depends(TemplateEditor),
    branch_id: int | None = Query(default=None),
) -> EmailTemplateResponse:
    if template_key not in DEFAULT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email template")
    scope = _resolve_scope(current_user, branch_id, default_to_own_branch=True)
    return _template_response(db, current_user, template_key, scope)


@router.put(
    "/{template_key}",
    response_model=EmailTemplateResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def update_email_template(
    template_key: str,
    payload: EmailTemplateUpdate,
    db: DatabaseSession,
    current_user: User = Depends(TemplateEditor),
) -> EmailTemplateResponse:
    if template_key not in DEFAULT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email template")
    scope = _resolve_scope(current_user, payload.branch_id, default_to_own_branch=True)
    if scope is not None and db.get(Branch, scope) is None:
        raise HTTPException(status_code=404, detail="Branch not found")

    try:
        validate_template(template_key, payload.subject_template, payload.html_body)
    except EmailTemplateError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    row = _load_row(db, template_key, scope)
    definition = DEFAULT_TEMPLATES[template_key]
    if row is None:
        row = EmailTemplate(
            template_key=template_key,
            branch_id=scope,
            name=definition.name,
        )
        db.add(row)
    row.subject_template = payload.subject_template
    row.html_body = payload.html_body
    row.text_body = payload.text_body or html_to_text(payload.html_body)
    row.is_active = payload.is_active
    row.updated_by_id = current_user.id
    db.flush()

    record_audit(
        db,
        current_user.id,
        "email_template_updated",
        "email_template",
        row.id,
        {
            "template_key": template_key,
            "branch_id": scope,
            "scope": "global" if scope is None else "branch",
        },
    )
    db.commit()
    return _template_response(db, current_user, template_key, scope)


@router.delete(
    "/{template_key}",
    response_model=EmailTemplateResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def reset_email_template(
    template_key: str,
    db: DatabaseSession,
    current_user: User = Depends(TemplateEditor),
    branch_id: int | None = Query(default=None),
) -> EmailTemplateResponse:
    if template_key not in DEFAULT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email template")
    scope = _resolve_scope(current_user, branch_id, default_to_own_branch=True)
    if scope is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "The global default cannot be deleted. Edit it, or reset a "
                "branch override from the branch scope."
            ),
        )
    row = _load_row(db, template_key, scope)
    if row is None:
        raise HTTPException(
            status_code=404, detail="This branch does not have an override to reset"
        )
    record_audit(
        db,
        current_user.id,
        "email_template_reset",
        "email_template",
        row.id,
        {"template_key": template_key, "branch_id": scope},
    )
    db.delete(row)
    db.commit()
    return _template_response(db, current_user, template_key, scope)


@router.post(
    "/{template_key}/preview",
    response_model=EmailTemplatePreviewResponse,
    dependencies=[Depends(NotificationsAccess)],
)
def preview_email_template(
    template_key: str,
    payload: EmailTemplatePreviewRequest,
    db: DatabaseSession,
    current_user: User = Depends(TemplateEditor),
) -> EmailTemplatePreviewResponse:
    if template_key not in DEFAULT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email template")
    # Preview is read-only, but still validate scope so a branch user cannot
    # probe another branch's override.
    _resolve_scope(current_user, payload.branch_id, default_to_own_branch=True)

    warnings: list[str] = []
    try:
        validate_template(template_key, payload.subject_template, payload.html_body)
        rendered = render_email_content(
            template_key,
            subject_template=payload.subject_template,
            html_body=payload.html_body,
            text_body=payload.text_body,
            context=SAMPLE_CONTEXTS.get(template_key, {}),
            name=DEFAULT_TEMPLATES[template_key].name,
            source="preview",
        )
    except EmailTemplateError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if "{{" in rendered.subject or "{{" in rendered.html:
        warnings.append("Some variables were left blank because no sample value exists.")
    missing = [
        token
        for token in DEFAULT_TEMPLATES[template_key].required
        if token not in payload.html_body and token not in payload.subject_template
    ]
    if missing:
        warnings.append(
            "Required variables missing: "
            + ", ".join("{{" + item + "}}" for item in missing)
        )
    return EmailTemplatePreviewResponse(
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        warnings=warnings,
    )
