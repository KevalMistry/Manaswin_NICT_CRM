"""Editable outbound email templates and a single rendering/delivery path.

Every email the application sends should go through :func:`render_email` and
:func:`send_templated_email`. Templates are stored globally and can be
overridden per branch by Super Admin, Branch Admin or Staff.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.fee import EmailTemplate
from app.models.notification import NotificationLog
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    send_email,
)


TOKEN_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
# Context values that already contain trusted, pre-escaped HTML fragments.
HTML_SAFE_TOKENS = frozenset({"reminder_rows"})


class EmailTemplateError(ValueError):
    """Raised when a template references an unknown or missing variable."""


@dataclass
class RenderedEmail:
    key: str
    name: str
    subject: str
    html: str
    text: str
    source: str


@dataclass
class TemplateDefinition:
    key: str
    name: str
    subject: str
    html: str
    variables: tuple[str, ...]
    required: tuple[str, ...]


def _page(title: str, intro: str, rows: str, footer: str = "") -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#27374c">
  <div style="max-width:620px;margin:0 auto;padding:24px 14px">
    <div style="background:#132742;color:#ffffff;border-radius:14px 14px 0 0;padding:24px 28px">
      <div style="font-size:11px;letter-spacing:2px;color:#8bb4ff;text-transform:uppercase">NICT Institute</div>
      <h1 style="margin:8px 0 0;font-size:23px;line-height:1.25">{escape(title)}</h1>
    </div>
    <div style="background:#ffffff;border:1px solid #e5eaf1;border-top:0;border-radius:0 0 14px 14px;padding:26px 28px">
      <p style="margin:0 0 18px;font-size:14px;line-height:1.7">{intro}</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px">{rows}</table>
      {footer}
    </div>
    <p style="text-align:center;color:#93a1b3;font-size:11px;margin:16px 0 0">
      This is an automated message from NICT Institute.
    </p>
  </div>
</body></html>"""


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:8px 0;color:#718097;border-bottom:1px solid #eef2f7">{escape(label)}</td>'
        f'<td style="padding:8px 0;text-align:right;font-weight:600;color:#27374c;border-bottom:1px solid #eef2f7">{value}</td></tr>'
    )


DEFAULT_TEMPLATES: dict[str, TemplateDefinition] = {
    "fee_receipt": TemplateDefinition(
        key="fee_receipt",
        name="Fee payment receipt",
        subject="Fee receipt {{receipt_number}} from {{branch_name}}",
        html=_page(
            "Payment received",
            "Dear {{student_name}}, we have received your fee payment. Your receipt is attached as a PDF.",
            _row("Receipt number", "{{receipt_number}}")
            + _row("Student", "{{student_name}} ({{student_code}})")
            + _row("Course / batch", "{{course_name}} / {{batch_name}}")
            + _row("Installment", "{{installment_number}}")
            + _row("Amount paid", "INR {{amount}}")
            + _row("Payment method", "{{payment_method}}")
            + _row("Payment date", "{{payment_date}}")
            + _row("UPI reference", "{{reference}}")
            + _row("Total fee", "INR {{total_fee}}")
            + _row("Total paid", "INR {{total_paid}}")
            + _row("Balance", "INR {{balance}}")
            + _row("Branch", "{{branch_name}}"),
            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "Keep this receipt for your records. If anything looks incorrect, contact "
            "{{branch_name}}{{branch_phone_suffix}}.</p>",
        ),
        variables=(
            "student_name", "student_code", "receipt_number", "course_name",
            "batch_name", "installment_number", "amount", "payment_method",
            "payment_date", "reference", "total_fee", "total_paid", "balance",
            "branch_name", "branch_address", "branch_phone", "branch_gstin",
            "branch_phone_suffix",
        ),
        required=("student_name", "receipt_number", "amount", "branch_name"),
    ),
    "fee_reminder": TemplateDefinition(
        key="fee_reminder",
        name="Fee payment reminder",
        subject="Fee payment reminder from {{branch_name}}",
        html=_page(
            "Fee payment reminder",
            "Dear {{student_name}}, this is a friendly reminder about your pending fee installment(s).",
            "{{reminder_rows}}"
            + _row("Total pending", "INR {{total_pending}}"),
            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "Please contact the branch office if you have already paid or need help.</p>",
        ),
        variables=("student_name", "branch_name", "reminder_rows", "total_pending"),
        required=("student_name", "reminder_rows", "total_pending"),
    ),
    "course_completion": TemplateDefinition(
        key="course_completion",
        name="Course completion notice",
        subject="{{course_name}} course completion — {{branch_name}}",
        html=_page(
            "Course completed",
            "Dear {{student_name}}, your {{course_name}} course ({{batch_name}}) reached its scheduled end date on {{end_date}}.",
            _row("Course", "{{course_name}}")
            + _row("Batch", "{{batch_name}}")
            + _row("Scheduled end", "{{end_date}}")
            + _row("Branch", "{{branch_name}}"),
            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "The institute is completing the final checks for your certificate "
            "(attendance, fees, examinations, assignments and online exams). "
            "You will be notified as soon as your certificate is ready.</p>",
        ),
        variables=("student_name", "course_name", "batch_name", "end_date", "branch_name"),
        required=("student_name", "course_name", "end_date"),
    ),
    "password_reset": TemplateDefinition(
        key="password_reset",
        name="Password reset link",
        subject="Reset your NICT Institute password",
        html=_page(
            "Reset your password",
            "Dear {{user_name}}, use the button below to set a new password. This link expires in {{expires_minutes}} minutes.",
            '<tr><td colspan="2" style="padding:20px 0 0;text-align:center">'
            '<a href="{{reset_link}}" style="display:inline-block;background:#3978e8;color:#ffffff;'
            'text-decoration:none;font-weight:700;font-size:13px;padding:12px 22px;border-radius:8px">'
            "Set a new password</a></td></tr>",
            '<p style="margin:18px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "If you did not request this, you can ignore this email. "
            "For security, do not forward this link to anyone.</p>",
        ),
        variables=("user_name", "reset_link", "expires_minutes"),
        required=("reset_link",),
    ),
    "payment_rejected": TemplateDefinition(
        key="payment_rejected",
        name="UPI payment claim rejected",
        subject="UPI payment could not be verified — {{course_name}}",
        html=_page(
            "Payment not verified",
            "Dear {{student_name}}, we could not verify your UPI payment claim for {{course_name}} ({{batch_name}}).",
            _row("Amount claimed", "INR {{amount}}")
            + _row("UPI reference", "{{upi_reference}}")
            + _row("Reason", "{{rejection_reason}}")
            + _row("Branch", "{{branch_name}}"),
            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "No payment has been recorded and your balance is unchanged. If money left "
            "your account, contact {{branch_name}}{{branch_phone_suffix}} with your UTR "
            "before trying again.</p>",
        ),
        variables=(
            "student_name", "course_name", "batch_name", "amount", "upi_reference",
            "rejection_reason", "branch_name", "branch_phone_suffix",
        ),
        required=("student_name", "amount", "upi_reference", "rejection_reason"),
    ),
    "payment_awaiting_verification": TemplateDefinition(
        key="payment_awaiting_verification",
        name="UPI payment awaiting verification",
        subject="UPI payment submitted for verification — {{course_name}}",
        html=_page(
            "Payment submitted",
            "Dear {{student_name}}, your UPI payment details have been submitted for verification.",
            _row("Amount", "INR {{amount}}")
            + _row("UPI reference", "{{upi_reference}}")
            + _row("Course / batch", "{{course_name}} / {{batch_name}}")
            + _row("Branch", "{{branch_name}}"),
            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#718097">'
            "This is not a receipt. Once the branch confirms the payment in its bank "
            "account, a receipt will be emailed to you automatically.</p>",
        ),
        variables=(
            "student_name", "course_name", "batch_name", "amount",
            "upi_reference", "branch_name",
        ),
        required=("student_name", "amount", "upi_reference"),
    ),
}


def _template_variables(key: str) -> set[str]:
    definition = DEFAULT_TEMPLATES.get(key)
    if definition is None:
        raise EmailTemplateError(f"Unknown email template '{key}'")
    return set(definition.variables)


def validate_template(key: str, subject: str, html: str) -> None:
    allowed = _template_variables(key)
    body = f"{subject}\n{html}"
    found = set(TOKEN_PATTERN.findall(body))
    unknown = sorted(found - allowed)
    if unknown:
        raise EmailTemplateError(
            "Unknown template variable(s): " + ", ".join("{{" + item + "}}" for item in unknown)
        )
    missing = [
        token for token in DEFAULT_TEMPLATES[key].required if token not in found
    ]
    if missing:
        raise EmailTemplateError(
            "The template must keep these variable(s): "
            + ", ".join("{{" + item + "}}" for item in missing)
        )


def html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</(p|tr|h1|h2|div)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _scope_key(branch_id: int | None) -> tuple[int | None]:
    return (branch_id,)


def _find_template(
    db: Session, key: str, branch_id: int | None
) -> tuple[EmailTemplate | None, str]:
    if branch_id is not None:
        row = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.template_key == key,
                EmailTemplate.branch_id == branch_id,
                EmailTemplate.is_active.is_(True),
            )
        )
        if row is not None:
            return row, "branch"
    row = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.template_key == key,
            EmailTemplate.branch_id.is_(None),
            EmailTemplate.is_active.is_(True),
        )
    )
    if row is not None:
        return row, "global"
    return None, "builtin"


def render_email_content(
    key: str,
    *,
    subject_template: str,
    html_body: str,
    text_body: str | None,
    context: dict[str, object],
    name: str | None = None,
    source: str = "custom",
) -> RenderedEmail:
    definition = DEFAULT_TEMPLATES.get(key)
    if definition is None:
        raise EmailTemplateError(f"Unknown email template '{key}'")
    text = text_body or html_to_text(html_body)

    def value_for(token: str) -> str:
        if token not in definition.variables:
            raise EmailTemplateError(f"Unknown template variable '{{{{{token}}}}}'")
        value = context.get(token, "")
        return "" if value is None else str(value)

    def replace_text(match: re.Match[str]) -> str:
        return value_for(match.group(1))

    def replace_html(match: re.Match[str]) -> str:
        token = match.group(1)
        value = value_for(token)
        # Context values are user-controlled (names, courses, messages). Escape
        # them before inserting into HTML so a crafted name cannot inject markup
        # or links into an email. ``reminder_rows`` is the one value that is
        # already a trusted, pre-escaped HTML fragment.
        if token in HTML_SAFE_TOKENS:
            return value
        return escape(value)

    return RenderedEmail(
        key=key,
        name=name or definition.name,
        subject=TOKEN_PATTERN.sub(replace_text, subject_template),
        html=TOKEN_PATTERN.sub(replace_html, html_body),
        text=TOKEN_PATTERN.sub(replace_text, text),
        source=source,
    )


def render_email(
    db: Session,
    key: str,
    context: dict[str, object],
    branch_id: int | None = None,
) -> RenderedEmail:
    row, source = _find_template(db, key, branch_id)
    if row is None:
        definition = DEFAULT_TEMPLATES.get(key)
        if definition is None:
            raise EmailTemplateError(f"Unknown email template '{key}'")
        return render_email_content(
            key,
            subject_template=definition.subject,
            html_body=definition.html,
            text_body=None,
            context=context,
            name=definition.name,
            source="builtin",
        )
    return render_email_content(
        key,
        subject_template=row.subject_template,
        html_body=row.html_body,
        text_body=row.text_body,
        context=context,
        name=row.name,
        source=source,
    )


def ensure_email_templates_seeded(db: Session) -> None:
    """Create the global default row for every known email template."""
    changed = False
    for key, definition in DEFAULT_TEMPLATES.items():
        existing = db.scalar(
            select(EmailTemplate.id).where(
                EmailTemplate.template_key == key,
                EmailTemplate.branch_id.is_(None),
            )
        )
        if existing is None:
            db.add(
                EmailTemplate(
                    template_key=key,
                    branch_id=None,
                    name=definition.name,
                    subject_template=definition.subject,
                    html_body=definition.html,
                    text_body=html_to_text(definition.html),
                    is_active=True,
                )
            )
            changed = True
    if changed:
        db.commit()


def send_templated_email(
    db: Session,
    *,
    key: str,
    recipient: str,
    context: dict[str, object],
    branch_id: int | None = None,
    category: str | None = None,
    student_id: int | None = None,
    enrollment_id: int | None = None,
    triggered_by_id: int | None = None,
    dry_run: bool = False,
    attachments: Iterable[tuple[str, bytes, str]] = (),
) -> tuple[str, str | None]:
    """Render and send one email, always writing a delivery log.

    Returns ``(status, detail)`` where status is ``sent``, ``dry_run`` or
    ``failed``. Delivery failures are reported to the caller instead of being
    swallowed; the caller decides whether the surrounding business action
    should still succeed.
    """
    rendered = render_email(db, key, context, branch_id=branch_id)
    status = "sent"
    detail: str | None = None
    if dry_run:
        status = "dry_run"
        detail = "Dry run: SMTP was not contacted."
    else:
        try:
            send_email(
                recipient,
                rendered.subject,
                rendered.text,
                rendered.html,
                attachments=list(attachments),
            )
        except MailNotConfigured as error:
            status = "failed"
            detail = str(error)
        except MailDeliveryError as error:
            status = "failed"
            detail = str(error)
        except Exception as error:  # pragma: no cover - defensive
            status = "failed"
            detail = f"Unexpected delivery error: {error}"

    db.add(
        NotificationLog(
            category=category or key,
            template_key=key,
            channel="email",
            status=status,
            recipient=recipient,
            subject=rendered.subject,
            message=rendered.text,
            error=detail if status == "failed" else None,
            branch_id=branch_id,
            student_id=student_id,
            enrollment_id=enrollment_id,
            triggered_by_id=triggered_by_id,
        )
    )
    db.flush()
    if status == "failed":
        raise MailDeliveryError(detail or "Email delivery failed")
    return status, detail


def template_branch_context(db: Session, branch: Branch | None) -> str:
    if branch is None:
        return ""
    return f" · {branch.name}" if branch.name else ""


def format_reminder_rows(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    cells = "".join(
        "<tr>"
        f'<td style="padding:8px 6px;border-bottom:1px solid #eef2f7">{escape(row["course"])}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eef2f7">{escape(row["installment"])}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eef2f7">{escape(row["amount"])}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eef2f7">{escape(row["due"])}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eef2f7">{escape(row["status"])}</td>'
        "</tr>"
        for row in rows
    )
    return (
        '<tr><th style="text-align:left;padding:8px 6px;font-size:11px;color:#718097">Course</th>'
        '<th style="text-align:left;padding:8px 6px;font-size:11px;color:#718097">Inst.</th>'
        '<th style="text-align:left;padding:8px 6px;font-size:11px;color:#718097">Amount</th>'
        '<th style="text-align:left;padding:8px 6px;font-size:11px;color:#718097">Due</th>'
        '<th style="text-align:left;padding:8px 6px;font-size:11px;color:#718097">Status</th></tr>'
        + cells
    )


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
