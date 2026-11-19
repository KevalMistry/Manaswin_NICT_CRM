"""Render issued certificates and marksheets as downloadable PDFs.

The institute does not store generated documents on disk. Instead, every
download is rendered from the certificate record, which keeps the document in
sync with the database and avoids stale files when a record is corrected.

ReportLab is used so the result is a real PDF that can be printed, archived or
attached to an email, rather than a print-only HTML page.
"""
from __future__ import annotations

import os
import base64
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from app.services.certificate_templates import marks_table_html, render_template


NAVY = HexColor("#172a43")
BLUE = HexColor("#3978e8")
GOLD = HexColor("#c19a3d")
MUTED = HexColor("#6b7c8f")
LINE = HexColor("#dbe3ee")
PALE_BLUE = HexColor("#f3f7fd")
WHITE = HexColor("#ffffff")

FONT_SERIF = "Helvetica"
FONT_SERIF_BOLD = "Helvetica-Bold"
FONT_SERIF_ITALIC = "Helvetica-Oblique"
FONT_SANS = "Helvetica"
FONT_SANS_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    """Prefer system DejaVu/Liberation fonts, but keep ReportLab defaults as a
    fallback so the document still renders on a machine without them."""

    global FONT_SERIF, FONT_SERIF_BOLD, FONT_SERIF_ITALIC, FONT_SANS, FONT_SANS_BOLD

    candidates = {
        "serif": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Regular.ttf",
        ),
        "serif_bold": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Bold.ttf",
        ),
        "serif_italic": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Italic.ttf",
        ),
        "sans": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
        ),
        "sans_bold": (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
        ),
    }

    def first_existing(paths: tuple[str, ...]) -> str | None:
        return next((path for path in paths if os.path.exists(path)), None)

    registrations = (
        ("DivisionSerif", "serif", FONT_SERIF),
        ("DivisionSerifBold", "serif_bold", FONT_SERIF_BOLD),
        ("DivisionSerifItalic", "serif_italic", FONT_SERIF_ITALIC),
        ("DivisionSans", "sans", FONT_SANS),
        ("DivisionSansBold", "sans_bold", FONT_SANS_BOLD),
    )
    registered: dict[str, str] = {}
    for font_name, key, fallback in registrations:
        path = first_existing(candidates[key])
        if path is None:
            registered[key] = fallback
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, path))
            registered[key] = font_name
        except Exception:
            registered[key] = fallback

    FONT_SERIF = registered["serif"]
    FONT_SERIF_BOLD = registered["serif_bold"]
    FONT_SERIF_ITALIC = registered["serif_italic"]
    FONT_SANS = registered["sans"]
    FONT_SANS_BOLD = registered["sans_bold"]


_register_fonts()


@dataclass(frozen=True)
class SubjectResult:
    examination: str
    subject: str
    marks_obtained: float
    maximum_marks: float
    grade: str | None


@dataclass(frozen=True)
class CertificateDocumentData:
    document_type: str
    certificate_number: str
    verification_code: str
    issue_date: date
    grade: str | None
    percentage: float | None
    digital_signature: str | None
    is_valid: bool
    student_name: str
    student_code: str
    course_name: str
    course_duration_months: int | None
    batch_name: str
    branch_name: str
    branch_address: str | None
    branch_phone: str | None
    branch_email: str | None
    admission_date: date | None
    verification_url: str
    subjects: list[SubjectResult] = field(default_factory=list)
    certificate_title: str | None = None
    marksheet_title: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    html_template: str | None = None


def _format_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d %B %Y").lstrip("0")


def _format_percentage(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _fit_font_size(
    text: str,
    font: str,
    size: float,
    max_width: float,
    minimum: float = 8,
) -> float:
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _ellipsize(text: str, font: str, size: float, max_width: float) -> str:
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    while text and pdfmetrics.stringWidth(f"{text}{ellipsis}", font, size) > max_width:
        text = text[:-1]
    return f"{text.rstrip()}{ellipsis}" if text else ellipsis


def _centered(
    pdf: canvas.Canvas,
    text: str,
    y: float,
    font: str,
    size: float,
    color=NAVY,
    center_x: float | None = None,
) -> None:
    if not text:
        return
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    pdf.drawCentredString(
        center_x if center_x is not None else pdf._pagesize[0] / 2,
        y,
        str(text),
    )


def _wrapped_centered(
    pdf: canvas.Canvas,
    text: str,
    y: float,
    font: str,
    size: float,
    color,
    max_width: float,
    leading: float,
) -> float:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or pdfmetrics.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        _centered(pdf, line, y, font, size, color)
        y -= leading
    return y


def _label(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    size: float = 7.5,
    color=MUTED,
    font: str | None = None,
) -> None:
    pdf.setFont(font or FONT_SANS, size)
    pdf.setFillColor(color)
    pdf.drawString(x, y, text)


def _tracked(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font: str,
    size: float,
    color=NAVY,
    tracking: float = 0.0,
    align: str = "left",
) -> None:
    """Draw text with optional letter spacing.

    ``Canvas.setCharSpace`` does not exist in ReportLab; character spacing is a
    text-object property, so tracked text is drawn through a text object.
    """
    width = pdfmetrics.stringWidth(text, font, size)
    if tracking:
        width += tracking * max(len(text) - 1, 0)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    text_object = pdf.beginText()
    text_object.setTextOrigin(x, y)
    text_object.setFont(font, size)
    text_object.setFillColor(color)
    if tracking:
        text_object.setCharSpace(tracking)
    text_object.textOut(text)
    pdf.drawText(text_object)
    if tracking:
        # ``Tc`` is a text-state parameter and survives ET, so reset it before
        # the next ordinary drawString call.
        reset = pdf.beginText()
        reset.setCharSpace(0)
        pdf.drawText(reset)


def _draw_qr(pdf: canvas.Canvas, data: str, x: float, y: float, size: float) -> None:
    widget = QrCodeWidget(data, barLevel="M")
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, pdf, x, y)


def _draw_border(pdf: canvas.Canvas, width: float, height: float) -> None:
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(2.4)
    pdf.rect(28, 28, width - 56, height - 56)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.9)
    pdf.rect(37, 37, width - 74, height - 74)
    pdf.setStrokeColor(HexColor("#e8ddbd"))
    pdf.setLineWidth(0.5)
    pdf.rect(42, 42, width - 84, height - 84)

    # Small gold corner accents.
    pdf.setFillColor(GOLD)
    corner = 7
    for x, y in (
        (37, 37),
        (width - 37 - corner, 37),
        (37, height - 37 - corner),
        (width - 37 - corner, height - 37 - corner),
    ):
        pdf.rect(x, y, corner, corner, fill=1, stroke=0)


def _draw_revoked(pdf: canvas.Canvas, width: float, height: float) -> None:
    pdf.saveState()
    pdf.translate(width / 2, height / 2)
    pdf.rotate(28)
    pdf.setFillColor(Color(0.78, 0.15, 0.15, alpha=0.16))
    pdf.setFont(FONT_SANS_BOLD, 82)
    pdf.drawCentredString(0, -20, "VOID")
    pdf.restoreState()


def _draw_institute_header(
    pdf: canvas.Canvas,
    data: CertificateDocumentData,
    width: float,
    top: float,
) -> None:
    center_x = width / 2
    pdf.setFillColor(NAVY)
    pdf.circle(center_x, top, 19, fill=1, stroke=0)
    pdf.setFillColor(WHITE)
    pdf.setFont(FONT_SERIF_BOLD, 18)
    pdf.drawCentredString(center_x, top - 6, "N")

    pdf.setFillColor(NAVY)
    _tracked(
        pdf,
        "NICT",
        center_x,
        top - 39,
        FONT_SANS_BOLD,
        15,
        NAVY,
        tracking=3.5,
        align="center",
    )

    pdf.setFont(FONT_SANS, 10.5)
    pdf.setFillColor(MUTED)
    pdf.drawCentredString(center_x, top - 56, data.branch_name)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.8)
    pdf.line(width / 2 - 150, top - 68, width / 2 + 150, top - 68)


def _draw_certificate(pdf: canvas.Canvas, data: CertificateDocumentData) -> None:
    width, height = landscape(A4)
    _draw_border(pdf, width, height)
    _draw_institute_header(pdf, data, width, height - 55)

    _centered(
        pdf,
        data.certificate_title or "CERTIFICATE",
        height - 178,
        FONT_SERIF_BOLD,
        35,
        NAVY,
    )
    _tracked(
        pdf,
        "OF COMPLETION",
        width / 2,
        height - 202,
        FONT_SANS_BOLD,
        10,
        GOLD,
        tracking=4.5,
        align="center",
    )

    _centered(pdf, "This is to certify that", height - 244, FONT_SERIF_ITALIC, 11.5, MUTED)

    name_size = _fit_font_size(data.student_name, FONT_SERIF_BOLD, 31, width - 170, 14)
    _centered(pdf, data.student_name, height - 282, FONT_SERIF_BOLD, name_size, NAVY)

    _centered(
        pdf,
        "has successfully completed the program",
        height - 310,
        FONT_SERIF,
        11.5,
        MUTED,
    )

    course_size = _fit_font_size(data.course_name, FONT_SANS_BOLD, 19, width - 220, 11)
    _centered(pdf, data.course_name, height - 338, FONT_SANS_BOLD, course_size, BLUE)

    branch_line = f"at {data.branch_name}"
    if data.course_duration_months:
        branch_line += f"  ·  {data.course_duration_months} month program"
    _centered(pdf, branch_line, height - 362, FONT_SANS, 10.5, MUTED)

    # Result panel.
    panel_y = height - 415
    pdf.setFillColor(PALE_BLUE)
    pdf.roundRect(width / 2 - 170, panel_y, 340, 42, 8, fill=1, stroke=0)
    pdf.setFillColor(LINE)
    pdf.rect(width / 2 - 0.5, panel_y + 8, 1, 26, fill=1, stroke=0)

    pdf.setFillColor(MUTED)
    _tracked(
        pdf,
        "GRADE",
        width / 2 - 85,
        panel_y + 26,
        FONT_SANS_BOLD,
        7,
        MUTED,
        tracking=1.2,
        align="center",
    )
    _tracked(
        pdf,
        "PERCENTAGE",
        width / 2 + 85,
        panel_y + 26,
        FONT_SANS_BOLD,
        7,
        MUTED,
        tracking=1.2,
        align="center",
    )
    pdf.setFillColor(NAVY)
    pdf.setFont(FONT_SERIF_BOLD, 18)
    pdf.drawCentredString(width / 2 - 85, panel_y + 10, data.grade or "—")
    pdf.drawCentredString(width / 2 + 85, panel_y + 10, _format_percentage(data.percentage))

    _centered(
        pdf,
        f"Issued on {_format_date(data.issue_date)}",
        height - 438,
        FONT_SANS,
        9.5,
        MUTED,
    )

    # Signature block.
    signature = (data.digital_signature or "").strip()
    if signature:
        signature_size = _fit_font_size(signature, FONT_SERIF_ITALIC, 13, 190, 8)
        _centered(
            pdf,
            signature,
            height - 491,
            FONT_SERIF_ITALIC,
            signature_size,
            NAVY,
            center_x=200,
        )
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.8)
    pdf.line(110, height - 500, 290, height - 500)
    _centered(
        pdf,
        "Authorised Signatory",
        height - 514,
        FONT_SANS,
        8,
        MUTED,
        center_x=200,
    )

    # Verification block and QR.
    _label(pdf, "CERTIFICATE NO.", 480, height - 477)
    pdf.setFont(FONT_SANS_BOLD, 9.5)
    pdf.setFillColor(NAVY)
    pdf.drawString(480, height - 489, data.certificate_number)
    _label(pdf, "VERIFICATION CODE", 480, height - 507)
    pdf.setFont(FONT_SANS, 8)
    pdf.setFillColor(NAVY)
    pdf.drawString(480, height - 519, data.verification_code)

    _draw_qr(pdf, data.verification_url, 690, height - 528, 50)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.7)
    pdf.line(80, 58, width - 80, 58)
    _wrapped_centered(
        pdf,
        f"Digitally generated document · Verify authenticity at {data.verification_url}",
        46,
        FONT_SANS,
        7.2,
        MUTED,
        width - 170,
        9,
    )

    if not data.is_valid:
        _draw_revoked(pdf, width, height)

    pdf.showPage()


def _draw_marksheet_header(
    pdf: canvas.Canvas,
    data: CertificateDocumentData,
    width: float,
    height: float,
    page_number: int,
) -> float:
    pdf.setFillColor(NAVY)
    pdf.circle(66, height - 55, 17, fill=1, stroke=0)
    pdf.setFillColor(WHITE)
    pdf.setFont(FONT_SERIF_BOLD, 16)
    pdf.drawCentredString(66, height - 61, "N")

    pdf.setFillColor(NAVY)
    _tracked(
        pdf,
        "NICT",
        92,
        height - 52,
        FONT_SANS_BOLD,
        12,
        NAVY,
        tracking=2.5,
    )
    pdf.setFont(FONT_SANS, 9)
    pdf.setFillColor(MUTED)
    pdf.drawString(92, height - 65, data.branch_name)

    pdf.setFont(FONT_SANS, 8)
    address = data.branch_address or ""
    if address:
        pdf.drawString(92, height - 77, _ellipsize(address, FONT_SANS, 8, width - 150))
    contact = " · ".join(
        part for part in (data.branch_phone, data.branch_email) if part
    )
    if contact:
        pdf.drawString(92, height - 88, _ellipsize(contact, FONT_SANS, 8, width - 150))

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.8)
    pdf.line(46, height - 100, width - 46, height - 100)

    _centered(
        pdf,
        data.marksheet_title or "STATEMENT OF MARKS",
        height - 128,
        FONT_SERIF_BOLD,
        21,
        NAVY,
    )
    _tracked(
        pdf,
        "ACADEMIC RECORD",
        width / 2,
        height - 143,
        FONT_SANS,
        7.4,
        MUTED,
        tracking=1.4,
        align="center",
    )
    if page_number > 1:
        pdf.setFont(FONT_SANS, 7.5)
        pdf.setFillColor(MUTED)
        pdf.drawRightString(width - 46, height - 128, f"Page {page_number}")
    return height - 160


def _draw_marksheet(pdf: canvas.Canvas, data: CertificateDocumentData) -> None:
    width, height = A4
    page_number = 1
    _draw_border(pdf, width, height)
    y = _draw_marksheet_header(pdf, data, width, height, page_number)

    # Student profile block.
    box_height = 92
    pdf.setFillColor(PALE_BLUE)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(46, y - box_height, width - 92, box_height, 6, fill=1, stroke=1)
    left_x = 60
    right_x = width / 2 + 12
    rows = (
        ("STUDENT", data.student_name, "STUDENT ID", data.student_code),
        ("COURSE", data.course_name, "BATCH", data.batch_name),
        ("ADMISSION DATE", _format_date(data.admission_date), "ISSUE DATE", _format_date(data.issue_date)),
    )
    row_y = y - 18
    for left_label, left_value, right_label, right_value in rows:
        _label(pdf, left_label, left_x, row_y)
        pdf.setFillColor(NAVY)
        pdf.setFont(FONT_SANS_BOLD, 9.5)
        pdf.drawString(left_x, row_y - 12, _ellipsize(str(left_value), FONT_SANS_BOLD, 9.5, 200))
        _label(pdf, right_label, right_x, row_y)
        pdf.setFillColor(NAVY)
        pdf.setFont(FONT_SANS_BOLD, 9.5)
        pdf.drawString(right_x, row_y - 12, _ellipsize(str(right_value), FONT_SANS_BOLD, 9.5, 200))
        row_y -= 28

    y -= box_height + 24

    # Table header.
    columns = (
        ("#", 50, 22, "left"),
        ("EXAMINATION", 74, 150, "left"),
        ("SUBJECT", 226, 150, "left"),
        ("MAX", 378, 52, "right"),
        ("OBTAINED", 434, 60, "right"),
        ("GRADE", 508, 40, "center"),
    )
    row_height = 21
    pdf.setFillColor(NAVY)
    pdf.rect(46, y - 19, width - 92, 21, fill=1, stroke=0)
    for title, x, col_width, align in columns:
        target_x = x + col_width if align == "right" else x + col_width / 2 if align == "center" else x
        _tracked(
            pdf,
            title,
            target_x,
            y - 12,
            FONT_SANS_BOLD,
            7,
            WHITE,
            tracking=0.4,
            align=align,
        )
    y -= 26

    if not data.subjects:
        pdf.setFillColor(MUTED)
        pdf.setFont(FONT_SANS, 9)
        pdf.drawCentredString(width / 2, y - 26, "No subject-wise marks are recorded for this enrollment.")
        y -= 52
    else:
        for index, subject in enumerate(data.subjects, start=1):
            if y < 260:
                pdf.showPage()
                page_number += 1
                _draw_border(pdf, width, height)
                y = _draw_marksheet_header(pdf, data, width, height, page_number)
                pdf.setFillColor(NAVY)
                pdf.rect(46, y - 19, width - 92, 21, fill=1, stroke=0)
                for title, x, col_width, align in columns:
                    target_x = (
                        x + col_width
                        if align == "right"
                        else x + col_width / 2
                        if align == "center"
                        else x
                    )
                    _tracked(
                        pdf,
                        title,
                        target_x,
                        y - 12,
                        FONT_SANS_BOLD,
                        7,
                        WHITE,
                        tracking=0.4,
                        align=align,
                    )
                y -= 26

            if index % 2 == 0:
                pdf.setFillColor(HexColor("#f8fafd"))
                pdf.rect(46, y - 17, width - 92, row_height, fill=1, stroke=0)
            pdf.setFillColor(NAVY)
            pdf.setFont(FONT_SANS, 8.5)
            pdf.drawString(50, y - 11, str(index))
            pdf.drawString(74, y - 11, _ellipsize(subject.examination, FONT_SANS, 8.5, 144))
            pdf.drawString(226, y - 11, _ellipsize(subject.subject, FONT_SANS, 8.5, 144))
            pdf.drawRightString(378 + 52, y - 11, f"{subject.maximum_marks:g}")
            pdf.drawRightString(434 + 60, y - 11, f"{subject.marks_obtained:g}")
            pdf.drawCentredString(508 + 20, y - 11, subject.grade or "—")
            pdf.setStrokeColor(HexColor("#edf0f4"))
            pdf.setLineWidth(0.4)
            pdf.line(46, y - 17, width - 46, y - 17)
            y -= row_height

    # Result summary.
    y -= 22
    pdf.setFillColor(PALE_BLUE)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(46, y - 62, width - 92, 62, 6, fill=1, stroke=1)
    total_obtained = sum(subject.marks_obtained for subject in data.subjects)
    total_maximum = sum(subject.maximum_marks for subject in data.subjects)
    summary = (
        ("TOTAL", f"{total_obtained:g} / {total_maximum:g}" if data.subjects else "—"),
        ("PERCENTAGE", _format_percentage(data.percentage)),
        ("OVERALL GRADE", data.grade or "—"),
    )
    cell_width = (width - 92) / len(summary)
    for index, (label, value) in enumerate(summary):
        cell_x = 46 + cell_width * index + cell_width / 2
        _tracked(
            pdf,
            label,
            cell_x,
            y - 24,
            FONT_SANS_BOLD,
            7,
            MUTED,
            tracking=1,
            align="center",
        )
        pdf.setFillColor(NAVY)
        pdf.setFont(FONT_SERIF_BOLD, 15)
        pdf.drawCentredString(cell_x, y - 45, value)

    # Footer: signature, certificate details and QR.
    footer_y = 120
    signature = (data.digital_signature or "").strip()
    if signature:
        signature_size = _fit_font_size(signature, FONT_SERIF_ITALIC, 11, 150, 7.5)
        pdf.setFillColor(NAVY)
        pdf.setFont(FONT_SERIF_ITALIC, signature_size)
        pdf.drawCentredString(135, footer_y + 22, signature)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.7)
    pdf.line(65, footer_y + 12, 205, footer_y + 12)
    pdf.setFillColor(MUTED)
    pdf.setFont(FONT_SANS, 7.5)
    pdf.drawCentredString(135, footer_y, "Authorised Signatory")

    _label(pdf, "CERTIFICATE NO.", 245, footer_y + 28)
    pdf.setFillColor(NAVY)
    pdf.setFont(FONT_SANS_BOLD, 9)
    pdf.drawString(245, footer_y + 17, data.certificate_number)
    _label(pdf, "VERIFICATION CODE", 245, footer_y + 3)
    pdf.setFont(FONT_SANS, 7.5)
    pdf.setFillColor(NAVY)
    pdf.drawString(245, footer_y - 7, data.verification_code)

    _draw_qr(pdf, data.verification_url, width - 110, footer_y - 10, 54)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.6)
    pdf.line(46, 52, width - 46, 52)
    _wrapped_centered(
        pdf,
        f"Digitally generated document · Verify authenticity at {data.verification_url}",
        40,
        FONT_SANS,
        6.8,
        MUTED,
        width - 110,
        8.5,
    )

    if not data.is_valid:
        _draw_revoked(pdf, width, height)

    pdf.showPage()


def render_certificate_document(data: CertificateDocumentData) -> bytes:
    """Return the PDF bytes for a certificate or marksheet record."""

    if data.html_template:
        rendered = _render_html_template(data)
        if rendered is not None:
            return rendered

    global NAVY, GOLD, BLUE
    previous_colors = (NAVY, GOLD, BLUE)
    if data.primary_color:
        NAVY = HexColor(data.primary_color)
        BLUE = NAVY
    if data.accent_color:
        GOLD = HexColor(data.accent_color)
    is_certificate = data.document_type == "certificate"
    try:
        buffer = BytesIO()
        pdf = canvas.Canvas(
            buffer,
            pagesize=landscape(A4) if is_certificate else A4,
            pageCompression=1,
        )
        pdf.setTitle(f"{data.certificate_number} · {data.student_name}")
        pdf.setAuthor("NICT")
        pdf.setSubject("Certificate" if is_certificate else "Statement of marks")
        pdf.setCreator("NICT Institute Management")

        if is_certificate:
            _draw_certificate(pdf, data)
        else:
            _draw_marksheet(pdf, data)

        pdf.save()
        return buffer.getvalue()
    finally:
        NAVY, GOLD, BLUE = previous_colors


def _render_html_template(data: CertificateDocumentData) -> bytes | None:
    """Render a sanitized template when the optional HTML PDF engine is installed.

    Returning ``None`` only means the deployment has not installed the optional
    renderer; the established ReportLab renderer remains the compatibility
    fallback for existing installations.
    """

    try:
        from xhtml2pdf import pisa
    except ImportError:
        return None

    import qrcode

    qr_image = qrcode.make(data.verification_url)
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_png = qr_buffer.getvalue()
    qr_html = f'<img src="data:image/png;base64,{base64.b64encode(qr_png).decode("ascii")}" style="width:72px;height:72px;" />'
    values = {
        "document_title": (
            data.certificate_title
            if data.document_type == "certificate"
            else data.marksheet_title
        )
        or ("CERTIFICATE" if data.document_type == "certificate" else "STATEMENT OF MARKS"),
        "certificate_title": data.certificate_title or "CERTIFICATE",
        "marksheet_title": data.marksheet_title or "STATEMENT OF MARKS",
        "primary_color": data.primary_color or "#172a43",
        "accent_color": data.accent_color or "#c19a3d",
        "student_name": data.student_name,
        "student_code": data.student_code,
        "course_name": data.course_name,
        "course_duration": str(data.course_duration_months or "—"),
        "batch_name": data.batch_name,
        "branch_name": data.branch_name,
        "branch_address": data.branch_address or "—",
        "branch_phone": data.branch_phone or "—",
        "branch_email": data.branch_email or "—",
        "certificate_number": data.certificate_number,
        "verification_code": data.verification_code,
        "issue_date": _format_date(data.issue_date),
        "admission_date": _format_date(data.admission_date),
        "grade": data.grade or "—",
        "percentage": _format_percentage(data.percentage),
        "digital_signature": data.digital_signature or "Authorised issuer",
        "verification_url": data.verification_url,
        "verification_qr": qr_html,
        "marks_table": marks_table_html(
            [
                {
                    "examination": subject.examination,
                    "subject": subject.subject,
                    "marks_obtained": str(subject.marks_obtained),
                    "maximum_marks": str(subject.maximum_marks),
                    "grade": subject.grade or "—",
                }
                for subject in data.subjects
            ]
        ),
    }
    html = render_template(
        data.html_template,
        values,
        raw_keys=frozenset({"marks_table", "verification_qr"}),
    )
    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>@page { size: A4 landscape; margin: 18mm; } "
        "table, th, td { border: 1px solid #dbe3ee; padding: 6px; } "
        "th { background: #f3f7fd; }</style></head><body>"
        f"{html}</body></html>"
    )
    buffer = BytesIO()
    result = pisa.CreatePDF(document, dest=buffer)
    if result.err:
        raise RuntimeError("The saved certificate template could not be rendered as a PDF")
    return buffer.getvalue()
