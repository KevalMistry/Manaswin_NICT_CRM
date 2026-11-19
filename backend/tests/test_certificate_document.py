import unittest
from datetime import date

from app.services.certificate_document import (
    CertificateDocumentData,
    SubjectResult,
    render_certificate_document,
)


def sample_document(**overrides) -> CertificateDocumentData:
    values = dict(
        certificate_number="CERT-2026-ABC123",
        verification_code="4f8e2a1c9b7d6e5f4a3b2c1d0e9f8a7b",
        issue_date=date(2026, 10, 25),
        grade="A",
        percentage=85.0,
        digital_signature="Demo Director",
        is_valid=True,
        student_name="Ishika",
        student_code="STU-2026-07E8067C",
        course_name="Full Stack Python Development",
        course_duration_months=6,
        batch_name="Python Morning Batch",
        branch_name="Manaswin NICT Vapi",
        branch_address="2nd Floor, Prime Plaza, Vapi, Gujarat",
        branch_phone="+91 98765 43210",
        branch_email="vapi@manaswinnict.com",
        admission_date=date(2026, 9, 25),
        verification_url=(
            "http://127.0.0.1:5173/verify-certificate?code="
            "4f8e2a1c9b7d6e5f4a3b2c1d0e9f8a7b"
        ),
    )
    values.update(overrides)
    return CertificateDocumentData(**values)


class CertificateDocumentTests(unittest.TestCase):
    def test_certificate_renders_as_landscape_pdf(self) -> None:
        pdf = render_certificate_document(
            sample_document(document_type="certificate")
        )

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"/Type /Page", pdf)
        self.assertIn(b"/MediaBox [ 0 0 841.8898 595.2756 ]", pdf)

    def test_marksheet_renders_as_portrait_pdf_with_subject_rows(self) -> None:
        pdf = render_certificate_document(
            sample_document(
                document_type="marksheet",
                subjects=[
                    SubjectResult(
                        examination="Python Fundamentals",
                        subject="Python Programming",
                        marks_obtained=88,
                        maximum_marks=100,
                        grade="A",
                    ),
                    SubjectResult(
                        examination="Web Development",
                        subject="FastAPI",
                        marks_obtained=91,
                        maximum_marks=100,
                        grade="A+",
                    ),
                ],
            )
        )

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"/MediaBox [ 0 0 595.2756 841.8898 ]", pdf)

    def test_optional_identity_fields_do_not_break_rendering(self) -> None:
        pdf = render_certificate_document(
            sample_document(
                document_type="marksheet",
                grade=None,
                percentage=None,
                digital_signature=None,
                branch_address=None,
                branch_phone=None,
                branch_email=None,
                admission_date=None,
                subjects=[],
            )
        )

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)


if __name__ == "__main__":
    unittest.main()
