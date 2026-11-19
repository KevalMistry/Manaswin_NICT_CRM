# Phase 2 delivery notes and remaining limitations

This document records what the Phase 2 build covers and which items from the
broader NICT specification are intentionally still open. It is written for the
next developer picking the project up.

## Delivered in Phase 2

| Area | What exists |
| --- | --- |
| LMS | Course modules, lessons (video/PDF/PPT/practice), quizzes, progress tracking, completion %, student **Learning** page |
| Assignments | Staff upload/publish assignments, students upload submissions, faculty marks + feedback, assignment completion feeds certificate eligibility |
| Certificates | Course durations in months, end date from `Batch.end_date` or `Enrollment.admission_date + duration`, certificate blocked before course end, Super Admin early-issue override, PDF + QR verification, auto-issue in the daily automation sweep |
| Attendance | Student QR sessions, staff attendance with branch geofence (default 150 m), optional office-network allowlist, IP/coordinate/accuracy captured, generic staff self-marking endpoint blocked |
| Online exams | Question banks, exams with snapshotted questions, timed attempts with auto-submit, results hidden until published, pass/fail feeds certificate eligibility |
| Notifications | Email + WhatsApp Cloud API channels, templated fee reminders/completion/certificate notices, 3-day reminder cooldown, preview + dry-run, live sends require `confirm_live` and a typed `SEND` |
| Parent portal | Admin-created parent accounts, parent/student links, read-only child progress, fees, attendance, published marks and remarks |
| Permissions | Layered role/module permissions: built-in role defaults, optional global overrides, then per-branch overrides; Branch Admins manage only their own branch and only Faculty/Staff/Counsellor |
| Placement | Companies, branch/course-eligible openings, applications pipeline, student self-apply, offer/interview tracking, placement report |
| Finance | Expenses with GST, bank accounts, cash book, summary (fees, expenses, net income, outstanding, GST payable, cash/bank), branch scoping |
| Franchise | Head-office franchise profiles per branch, royalty percentage, agreement dates, royalty settlements, franchise summary and report |
| Reports | 19 report definitions (admissions, enquiries, fees, pending fees, attendance, staff attendance, course completion, exams, placement, revenue + expense, GST, P&L, balance sheet, franchise) |
| Online admissions | Public apply/track page, private document upload with per-application token, admin review workspace, branch-scoped list/stats, manual or optional Razorpay registration-fee collection, GST invoice/receipt, one-step approval that creates the student, roll number, enrollment and course fee plan. Write actions are role-gated: staff/counsellors can review and approve, staff/branch admins can record payments, and only super/branch admins can reject or override an unpaid fee |

## Role points of view

| Role | Dashboard / entry point |
| --- | --- |
| Super Admin | Organisation-wide dashboard, all modules, franchise head-office view |
| Branch Admin | Branch-scoped dashboard and modules; no franchise module |
| Faculty | Faculty dashboard (batches, students, attendance, exams), LMS authoring, placement read, reports |
| Staff | Operations dashboard, students/fees/attendance/exams/certificates, finance, placement |
| Counsellor | CRM/enquiry dashboard, students, placement, reports; no finance or exams |
| Student | Student portal: attendance, fees, assignments, LMS, exams, certificates, placement opportunities |
| Parent | Parent portal: linked child progress, fees, attendance, published marks/remarks |

## Configuration defaults

- `AUTOMATION_ENABLED=false`, `AUTOMATION_DRY_RUN=true`. No email, WhatsApp,
  password-reset, or reminder message is sent in the default configuration.
- `AUTOMATION_CHANNELS=email`; set to `email,whatsapp` to enable WhatsApp.
- WhatsApp uses the Meta Cloud API (`WHATSAPP_TOKEN`,
  `WHATSAPP_PHONE_NUMBER_ID`, optional `WHATSAPP_API_URL`).
- `GST_RATE_PERCENT=18`. GST is treated as **inclusive** in fee/expense amounts
  and is derived only for reporting and admission invoices.
- `ADMISSION_PAYMENT_PROVIDER=manual` and `ADMISSION_PAYMENT_CURRENCY=INR`. The
  public form never calls an external gateway in this mode; the applicant is
  told to pay at the branch and staff record the payment in the admin
  workspace. Set `ADMISSION_PAYMENT_PROVIDER=razorpay` with
  `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` to activate the optional checkout.
- `AUTOMATION_AUTO_CERTIFICATES=true`; the certificate sweep follows the same
  dry-run/live rule as notifications.
- Uploads are stored on local disk under the backend uploads directory and
  served through the authenticated `/api/media/...` route. Stored database
  values keep the historical `/uploads/...` prefix, and the frontend maps them
  to the media route. Admission documents are stored separately under
  `backend/private_uploads/admissions` and are only reachable through the
  token-authenticated public endpoint or the authenticated admin endpoint.

## Still open from the full specification

1. **Online admission — remaining gaps** — the public form, document upload,
   review workflow, registration-fee collection and student creation exist.
   Still open: OTP/email verification of applicants, editable applicant
   resubmission, seat locking while an application is under review, automatic
   batch allocation, and applicant notifications when the status changes.
2. **Payments** — cash/UPI/bank/cheque/card are recorded manually and the
   optional Razorpay path is limited to the admission registration fee. No fee
   installment gateway, QR collection, EMI scheduling engine,
   scholarship/discount approval flow, or automatic receipt email/WhatsApp on
   payment.
3. **GST invoices** — printable GST invoices/receipts exist for admission
   registration fees. Course-fee GST invoices, credit notes, and
   e-invoicing/GSTR export are not implemented.
4. **Report volume** — 19 reports exist against the “100+” target. The report
   framework (`REPORT_DEFINITIONS`) is the extension point; most remaining
   reports are additional builders over existing data.
5. **Live classes** — no Zoom/Google Meet/Teams integration, live attendance,
   recordings, chat, whiteboard, or screen sharing.
6. **Attendance modes** — QR + GPS geofence + staff verification exist. Face
   recognition and biometric-device integration do not.
7. **Lead integrations** — Website, Facebook Lead Ads, Google Ads, and
   WhatsApp lead webhooks are not connected. Enquiries support manual lead
   sources and follow-ups only.
8. **Website CMS and company-owned centres** — not built.
9. **Mobile push notifications and SMS** — not built. Email and WhatsApp are
   the available channels today.
10. **Faculty portal** — faculty get a dedicated dashboard and module
    permissions, but there is no separate faculty-only URL or PWA. Faculty work
    is done through the shared admin shell.
11. **Finance depth** — single currency (INR), one global GST rate, no credit
    notes/refunds, bank reconciliation, TDS, or multi-account transfers.
12. **Franchise depth** — royalty is calculated on lifetime fee collections for
    the branch; settlements are recorded manually per period. No royalty
    invoice generation, automatic period accrual, or franchise self-service
    login.
13. **File storage** — local disk only; no S3/object storage or virus scanning.
14. **Messaging safety** — live sends are deliberately gated. Real delivery was
    not exercised during testing; SMTP and WhatsApp credentials must be
    configured and validated before enabling automation.

## Demo data preserved

The following pre-existing records were kept intact throughout testing:

- Branch `NICT Valsad` (id 9) and Branch Admin user 21.
- Students 1–4 and 24, enrollments 1, 2, 3, 19 and 27.
- Existing fee collections of ₹45,000 and the baseline ₹1,05,000 outstanding.
- Existing attendance and audit history outside the feature test rows.

All finance, franchise, placement and admission test rows created during
verification were removed, including their test audit entries, private uploaded
files and copied student documents. Course 1 `registration_fee` was restored to
`0.00` after the admission tests.
