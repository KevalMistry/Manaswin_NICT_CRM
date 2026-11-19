"""Fee receipt data, email context and PDF rendering shared by staff/student."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models.fee import Payment
from app.schemas.fee import ReceiptResponse


def money(value: Decimal | float | int | None) -> str:
    return f"{Decimal(value or 0):,.2f}"


def build_receipt(payment: Payment) -> ReceiptResponse:
    enrollment = payment.installment.fee_plan.enrollment
    plan = payment.installment.fee_plan
    total_paid = sum(
        (
            item.amount
            for installment in plan.installments
            for item in installment.payments
        ),
        Decimal("0"),
    )
    total_fee = plan.total_amount - plan.discount_amount - plan.scholarship_amount
    branch = enrollment.batch.branch
    return ReceiptResponse(
        payment_id=payment.id,
        receipt_number=payment.receipt_number,
        student_name=enrollment.student.full_name,
        student_code=enrollment.student.student_code,
        student_roll_number=enrollment.student.roll_number,
        student_email=enrollment.student.email,
        student_phone=enrollment.student.phone,
        course_name=enrollment.batch.course.name,
        batch_name=enrollment.batch.name,
        installment_number=payment.installment.installment_number,
        amount=payment.amount,
        payment_method=payment.payment_method,
        payment_date=payment.payment_date,
        reference=payment.reference,
        total_fee=total_fee,
        total_paid=total_paid,
        balance=total_fee - total_paid,
        branch_name=branch.name,
        branch_address=branch.address,
        branch_phone=branch.phone,
        branch_email=branch.email,
        branch_gstin=branch.gstin,
    )


def receipt_context(receipt: ReceiptResponse) -> dict[str, object]:
    method = receipt.payment_method.replace("_", " ").title()
    return {
        "student_name": receipt.student_name,
        "student_code": receipt.student_code,
        "student_roll_number": receipt.student_roll_number or "",
        "receipt_number": receipt.receipt_number,
        "course_name": receipt.course_name,
        "batch_name": receipt.batch_name,
        "installment_number": receipt.installment_number,
        "amount": money(receipt.amount),
        "payment_method": method,
        "payment_date": receipt.payment_date.isoformat(),
        "reference": receipt.reference or "—",
        "total_fee": money(receipt.total_fee),
        "total_paid": money(receipt.total_paid),
        "balance": money(receipt.balance),
        "branch_name": receipt.branch_name,
        "branch_address": receipt.branch_address or "",
        "branch_phone": receipt.branch_phone or "",
        "branch_phone_suffix": f" on {receipt.branch_phone}" if receipt.branch_phone else "",
        "branch_gstin": receipt.branch_gstin or "Not configured",
    }


def render_receipt_pdf(receipt: ReceiptResponse) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 46
    right = width - 46
    y = height - 54

    pdf.setFillColorRGB(0.075, 0.125, 0.2)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(left, y, "NICT Institute")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    pdf.drawString(left, y - 15, "Fee payment receipt")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColorRGB(0.22, 0.47, 0.91)
    pdf.drawRightString(right, y, receipt.receipt_number)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    pdf.drawRightString(right, y - 14, f"Payment date: {receipt.payment_date.isoformat()}")
    y -= 34
    pdf.setStrokeColorRGB(0.9, 0.92, 0.95)
    pdf.setLineWidth(1.4)
    pdf.line(left, y, right, y)
    y -= 30

    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left, y, "BRANCH")
    pdf.drawString(left + 280, y, "STUDENT")
    y -= 14
    pdf.setFillColorRGB(0.13, 0.2, 0.3)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left, y, receipt.branch_name[:38])
    pdf.drawString(left + 280, y, receipt.student_name[:34])
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    if receipt.branch_address:
        pdf.drawString(left, y - 13, receipt.branch_address[:48])
    details = [f"ID: {receipt.student_code}"]
    if receipt.student_roll_number:
        details.append(f"Roll: {receipt.student_roll_number}")
    if receipt.student_email:
        details.append(receipt.student_email[:42])
    pdf.drawString(left + 280, y - 13, " · ".join(details)[:62])
    y -= 44

    pdf.setFillColorRGB(0.95, 0.96, 0.98)
    pdf.rect(left, y - 10, right - left, 22, stroke=0, fill=1)
    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left + 8, y - 3, "DESCRIPTION")
    pdf.drawRightString(right - 8, y - 3, "AMOUNT (INR)")
    y -= 34
    pdf.setFillColorRGB(0.13, 0.2, 0.3)
    pdf.setFont("Helvetica", 10)
    description = (
        f"Fee installment {receipt.installment_number} · "
        f"{receipt.course_name} / {receipt.batch_name}"
    )
    pdf.drawString(left + 8, y, description[:78])
    pdf.drawRightString(right - 8, y, money(receipt.amount))
    y -= 18
    pdf.setStrokeColorRGB(0.9, 0.92, 0.95)
    pdf.line(left, y, right, y)
    y -= 26

    rows = [
        ("Payment method", receipt.payment_method.replace("_", " ").title()),
        ("UPI / payment reference", receipt.reference or "—"),
        ("Total course fee", f"INR {money(receipt.total_fee)}"),
        ("Total paid", f"INR {money(receipt.total_paid)}"),
        ("Balance", f"INR {money(receipt.balance)}"),
    ]
    for label, value in rows:
        pdf.setFillColorRGB(0.44, 0.5, 0.59)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(left + 8, y, label)
        pdf.setFillColorRGB(0.13, 0.2, 0.3)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawRightString(right - 8, y, str(value)[:58])
        y -= 17

    y -= 18
    pdf.setFillColorRGB(0.42, 0.5, 0.59)
    pdf.setFont("Helvetica", 8)
    footer = [
        "This is a computer-generated fee receipt. GST is included in the fee amount where applicable.",
        f"Branch: {receipt.branch_name}"
        + (f" · {receipt.branch_phone}" if receipt.branch_phone else "")
        + (f" · GSTIN {receipt.branch_gstin}" if receipt.branch_gstin else ""),
        f"Receipt {receipt.receipt_number} · generated from the NICT Institute management system.",
    ]
    for line in footer:
        pdf.drawString(left, y, line[:118])
        y -= 11

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
