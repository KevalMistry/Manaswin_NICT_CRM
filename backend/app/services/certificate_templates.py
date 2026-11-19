from __future__ import annotations

import re
from html import escape
from typing import Final

import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        "student_name",
        "student_code",
        "course_name",
        "course_duration",
        "batch_name",
        "branch_name",
        "branch_address",
        "branch_phone",
        "branch_email",
        "certificate_number",
        "verification_code",
        "issue_date",
        "admission_date",
        "grade",
        "percentage",
        "digital_signature",
        "marks_table",
        "verification_url",
        "verification_qr",
        "document_title",
        "certificate_title",
        "marksheet_title",
        "primary_color",
        "accent_color",
    }
)
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
DANGEROUS_CSS_PATTERN = re.compile(
    r"(?:url\s*\(|@import|expression\s*\(|javascript\s*:|-moz-binding)",
    re.IGNORECASE,
)

DEFAULT_CERTIFICATE_TEMPLATE = """<div style="font-family: Georgia, serif; text-align: center; border: 8px double {{accent_color}}; padding: 42px; color: {{primary_color}};">
<div style="font-size: 11px; letter-spacing: 3px; color: {{accent_color}};">{{branch_name}}</div>
<h1 style="font-size: 28px; margin: 24px 0 8px; color: {{primary_color}};">{{certificate_title}}</h1>
<p style="font-size: 15px;">This is proudly presented to</p>
<h2 style="font-size: 25px; margin: 12px 0; color: {{primary_color}};">{{student_name}}</h2>
<p>for successfully completing <strong>{{course_name}}</strong></p>
<div style="margin-top: 28px; font-size: 11px;">Issued on {{issue_date}} · Certificate No. {{certificate_number}}</div>
<div style="margin-top: 8px; font-size: 12px; font-style: italic;">{{digital_signature}}</div>
<div style="margin-top: 14px;">{{verification_qr}}</div>
</div>"""

DEFAULT_MARKSHEET_TEMPLATE = """<div style="font-family: Arial, sans-serif; border: 3px solid {{primary_color}}; padding: 26px; color: {{primary_color}};">
<div style="text-align: center; color: {{accent_color}}; letter-spacing: 2px;">{{branch_name}}</div>
<h1 style="text-align: center; margin: 20px 0; color: {{primary_color}};">{{marksheet_title}}</h1>
<p><strong>Student:</strong> {{student_name}} &nbsp; <strong>Course:</strong> {{course_name}}</p>
{{marks_table}}
<p style="text-align: right; color: {{primary_color}};">Percentage: {{percentage}} · Grade: {{grade}}</p>
<div style="margin-top: 14px; text-align: right;">
  <span style="font-size: 11px; float: left; margin-top: 10px;">Issued on {{issue_date}} · Certificate No. {{certificate_number}}</span>
  {{verification_qr}}
</div>
</div>"""

ALLOWED_TAGS: Final[frozenset[str]] = frozenset(
    set(bleach.sanitizer.ALLOWED_TAGS)
    | {"article", "div", "section", "header", "footer", "main", "table", "thead", "tbody", "tr", "th", "td", "h1", "h2", "h3", "p", "span", "strong", "em", "br", "hr", "style"}
)
ALLOWED_ATTRIBUTES: Final[dict[str, list[str]]] = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "*": ["class", "id", "style"],
}
CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties={
        "background",
        "background-color",
        "border",
        "border-color",
        "border-radius",
        "border-style",
        "border-width",
        "border-collapse",
        "border-spacing",
        "box-sizing",
        "clear",
        "color",
        "display",
        "float",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "height",
        "letter-spacing",
        "line-height",
        "margin",
        "margin-top",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "max-height",
        "max-width",
        "min-height",
        "min-width",
        "overflow",
        "padding",
        "padding-top",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "text-align",
        "text-decoration",
        "text-transform",
        "vertical-align",
        "white-space",
        "width",
    }
)


def sanitize_template(template: str | None, *, document_type: str) -> str:
    value = (template or "").strip()
    if not value:
        value = (
            DEFAULT_CERTIFICATE_TEMPLATE
            if document_type == "certificate"
            else DEFAULT_MARKSHEET_TEMPLATE
        )
    placeholders = set(PLACEHOLDER_PATTERN.findall(value))
    unknown = sorted(placeholders - ALLOWED_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Unsupported placeholders: {', '.join(unknown)}")
    if DANGEROUS_CSS_PATTERN.search(value):
        raise ValueError("Templates cannot load external resources or execute code")
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=[],
        strip=True,
        css_sanitizer=CSS_SANITIZER,
    )


def render_template(
    template: str,
    values: dict[str, str],
    raw_keys: frozenset[str] = frozenset(),
) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key, "")
        return value if key in raw_keys else escape(value)

    return PLACEHOLDER_PATTERN.sub(replace, template)


def marks_table_html(subjects: list[dict[str, str]]) -> str:
    rows = "".join(
        f"<tr><td>{escape(row['examination'])}</td><td>{escape(row['subject'])}</td>"
        f"<td>{escape(row['marks_obtained'])}</td><td>{escape(row['maximum_marks'])}</td>"
        f"<td>{escape(row['grade'])}</td></tr>"
        for row in subjects
    )
    return (
        '<table style="width:100%; border-collapse:collapse; margin:20px 0;">'
        "<thead><tr><th>Exam</th><th>Subject</th><th>Marks</th><th>Maximum</th><th>Grade</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
