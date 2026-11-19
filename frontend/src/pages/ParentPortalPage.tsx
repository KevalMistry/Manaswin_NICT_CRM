import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import {
  certificateErrorMessage,
  downloadCertificateDocument,
} from '../utils/certificateDocument'
import {
  certificateVerificationPath,
  countLabel,
  formatCertificateDate,
  formatCertificateResult,
} from '../utils/certificateUi'
import CertificatePreviewModal from '../components/CertificatePreviewModal'
import CopyButton from '../components/CopyButton'
import AuthImage from '../components/AuthImage'

type PortalEnrollment = {
  enrollment_id: number
  enrollment_code: string
  course_name: string
  batch_name: string
  status: string
  admission_date: string
  course_end_date: string | null
  days_remaining: number | null
  course_completed: boolean
  attendance_percentage: number
  progress_percent: number
  completed_lessons: number
  total_lessons: number
  total_fee: number | string
  total_paid: number | string
  balance: number | string
  next_due_date: string | null
  fee_status: string
}

type PortalAttendance = {
  enrollment_code: string
  total: number
  present: number
  late: number
  absent: number
  percentage: number
}

type PortalResult = {
  examination: string
  exam_date: string | null
  subject: string
  marks_obtained: number | string
  maximum_marks: number | string
  grade: string | null
}

type PortalCertificate = {
  id: number
  certificate_number: string
  verification_code: string
  document_type: string
  issue_date: string
  grade: string | null
  percentage: number | null
  is_valid: boolean
}

type PortalAssignment = {
  assignment_id: number
  title: string
  course_name: string
  due_date: string | null
  status: string
  submitted_at: string | null
  marks_obtained: number | string | null
  maximum_marks: number | string
  grade: string | null
  feedback: string | null
}

type PortalChild = {
  student_id: number
  student_code: string
  full_name: string
  photo_url: string | null
  branch_name: string
  relationship: string
  is_primary: boolean
  enrollments: PortalEnrollment[]
  attendance: PortalAttendance[]
  results: PortalResult[]
  assignments: PortalAssignment[]
  certificates: PortalCertificate[]
}

type ParentPortal = {
  parent_name: string
  email: string
  phone: string | null
  children: PortalChild[]
}

function formatMoney(value: number | string): string {
  return `₹${Number(value).toLocaleString('en-IN')}`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

function documentLabel(value: string): string {
  return value === 'certificate' ? 'Certificate' : 'Marksheet'
}

function ParentPortalPage() {
  const navigate = useNavigate()
  const [portal, setPortal] = useState<ParentPortal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [documentMessage, setDocumentMessage] = useState('')
  const [documentError, setDocumentError] = useState('')
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [preview, setPreview] = useState<PortalCertificate | null>(null)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      setError('')
      try {
        const { data } = await api.get<ParentPortal>('/api/parent-portal/me')
        if (active) setPortal(data)
      } catch (requestError) {
        if (active) {
          setError(
            apiErrorMessage(
              requestError,
              'Your parent portal is not available yet. Contact the institute office.',
            ),
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  function logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    navigate('/login', { replace: true })
  }

  async function download(certificate: PortalCertificate) {
    setDownloadingId(certificate.id)
    setDocumentError('')
    setDocumentMessage('')
    try {
      await downloadCertificateDocument(certificate.id, certificate.certificate_number)
      setDocumentMessage(`Downloaded ${certificate.certificate_number}.pdf`)
    } catch (requestError) {
      setDocumentError(
        certificateErrorMessage(
          requestError,
          'Unable to download this document. Please try again.',
        ),
      )
    } finally {
      setDownloadingId(null)
    }
  }

  if (loading) {
    return (
      <main className="student-shell">
        <div className="table-state">Loading your family portal…</div>
      </main>
    )
  }

  if (error || !portal) {
    return (
      <main className="student-shell">
        <div className="student-error">{error || 'Parent portal unavailable.'}</div>
      </main>
    )
  }

  return (
    <main className="student-shell">
      <header className="student-topbar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <strong>NICT</strong>
            <span>Parent Portal</span>
          </div>
        </div>
        <div className="student-account">
          <div className="avatar">{portal.parent_name.slice(0, 1).toUpperCase()}</div>
          <div>
            <strong>{portal.parent_name}</strong>
            <small>{portal.email}</small>
          </div>
          <button className="secondary-button" onClick={logout} type="button">
            Sign out
          </button>
        </div>
      </header>

      <div className="student-content">
        <div className="page-heading module-heading">
          <div>
            <span className="eyebrow">FAMILY OVERVIEW</span>
            <h1>{portal.parent_name}</h1>
            <p>
              Read-only progress for {portal.children.length}{' '}
              {portal.children.length === 1 ? 'child' : 'children'}.
              {portal.phone ? ` · ${portal.phone}` : ''}
            </p>
          </div>
        </div>

        {documentError && <div className="inline-error" role="alert">{documentError}</div>}
        {documentMessage && <div className="success-message" role="status">{documentMessage}</div>}

        {portal.children.map((child) => (
          <section className="data-panel student-section" key={child.student_id}>
            <div className="section-title parent-child-head">
              <div className="parent-child-identity">
                {child.photo_url ? (
                  <AuthImage alt="" className="parent-child-photo" path={child.photo_url} />
                ) : (
                  <div className="avatar">{child.full_name.slice(0, 1).toUpperCase()}</div>
                )}
                <div>
                  <h2>{child.full_name}</h2>
                  <span>
                    {child.student_code} · {child.branch_name} · {child.relationship}
                  </span>
                </div>
              </div>
              <span className="result-count">
                {child.enrollments.length} course{child.enrollments.length === 1 ? '' : 's'}
              </span>
            </div>

            <div className="parent-child-body">
              {child.enrollments.map((enrollment) => (
                <article className="student-card" key={enrollment.enrollment_id}>
                  <div className="student-learning-head">
                    <div>
                      <h3>{enrollment.course_name}</h3>
                      <span>
                        {enrollment.batch_name} · {enrollment.enrollment_code}
                      </span>
                    </div>
                    <span
                      className={`status-pill ${
                        enrollment.status === 'active' ? 'active-status' : 'inactive-status'
                      }`}
                    >
                      <i />
                      {enrollment.status}
                    </span>
                  </div>

                  <div className="student-fee-line">
                    <span>Admitted {formatDate(enrollment.admission_date)}</span>
                    <span>Ends {formatDate(enrollment.course_end_date)}</span>
                    <span>
                      {enrollment.course_completed
                        ? 'Course completed'
                        : enrollment.days_remaining !== null
                          ? `${enrollment.days_remaining} day(s) remaining`
                          : 'End date not set'}
                    </span>
                  </div>

                  <div className="parent-stat-row">
                    <div>
                      <span>Attendance</span>
                      <strong>{enrollment.attendance_percentage}%</strong>
                    </div>
                    <div>
                      <span>Progress</span>
                      <strong>{enrollment.progress_percent}%</strong>
                      <small>
                        {enrollment.completed_lessons}/{enrollment.total_lessons} lessons
                      </small>
                    </div>
                    <div>
                      <span>Course fee</span>
                      <strong>{formatMoney(enrollment.total_fee)}</strong>
                    </div>
                    <div>
                      <span>Balance</span>
                      <strong>{formatMoney(enrollment.balance)}</strong>
                    </div>
                  </div>

                  <div className="parent-progress-track" aria-hidden="true">
                    <i style={{ width: `${Math.min(enrollment.progress_percent, 100)}%` }} />
                  </div>

                  <div className="exam-chip-row">
                    <span
                      className={
                        enrollment.fee_status === 'Cleared'
                          ? 'exam-chip notification-status-ok'
                          : enrollment.fee_status === 'Overdue'
                            ? 'exam-chip notification-status-fail'
                            : 'exam-chip notification-status-preview'
                      }
                    >
                      Fees: {enrollment.fee_status}
                    </span>
                    {enrollment.next_due_date && enrollment.fee_status !== 'Cleared' && (
                      <span className="exam-chip">
                        Next due {formatDate(enrollment.next_due_date)}
                      </span>
                    )}
                  </div>
                </article>
              ))}
              {!child.enrollments.length && (
                <div className="table-state">
                  No course enrollments are linked to this student yet.
                </div>
              )}
            </div>

            <div className="parent-subsection">
              <div className="section-title">
                <div>
                  <span className="eyebrow">HOMEWORK</span>
                  <h2>Assignments and teacher remarks</h2>
                </div>
                <span className="result-count">{child.assignments.length} items</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Assignment</th>
                      <th>Course</th>
                      <th>Due</th>
                      <th>Status</th>
                      <th>Marks</th>
                      <th>Remarks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {child.assignments.map((assignment) => (
                      <tr key={assignment.assignment_id}>
                        <td>
                          <strong>{assignment.title}</strong>
                          {assignment.submitted_at && (
                            <small className="muted-block">
                              Submitted {formatDate(assignment.submitted_at.slice(0, 10))}
                            </small>
                          )}
                        </td>
                        <td>{assignment.course_name}</td>
                        <td>{formatDate(assignment.due_date)}</td>
                        <td>
                          <span
                            className={
                              assignment.status === 'Graded'
                                ? 'exam-chip notification-status-ok'
                                : assignment.status === 'Overdue'
                                  ? 'exam-chip notification-status-fail'
                                  : 'exam-chip'
                            }
                          >
                            {assignment.status}
                          </span>
                        </td>
                        <td>
                          {assignment.marks_obtained !== null
                            ? `${Number(assignment.marks_obtained)} / ${Number(assignment.maximum_marks)}`
                            : `— / ${Number(assignment.maximum_marks)}`}
                          {assignment.grade ? ` · ${assignment.grade}` : ''}
                        </td>
                        <td>
                          {assignment.feedback ? (
                            <span className="parent-remark">{assignment.feedback}</span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!child.assignments.length && (
                  <div className="table-state">
                    Homework appears here when the faculty publishes assignments.
                  </div>
                )}
              </div>
            </div>

            <div className="parent-subsection">
              <div className="section-title">
                <div>
                  <span className="eyebrow">RESULTS</span>
                  <h2>Published examination marks</h2>
                </div>
                <span className="result-count">{child.results.length} rows</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Examination</th>
                      <th>Date</th>
                      <th>Subject</th>
                      <th>Marks</th>
                      <th>Grade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {child.results.map((result, index) => (
                      <tr key={`${result.examination}-${result.subject}-${index}`}>
                        <td>{result.examination}</td>
                        <td>{formatDate(result.exam_date)}</td>
                        <td>{result.subject}</td>
                        <td>
                          {Number(result.marks_obtained)} / {Number(result.maximum_marks)}
                        </td>
                        <td>{result.grade ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!child.results.length && (
                  <div className="table-state">
                    Results appear here once the institute publishes them.
                  </div>
                )}
              </div>
            </div>

            <div className="parent-subsection">
              <div className="section-title">
                <div>
                  <span className="eyebrow">DOCUMENTS</span>
                  <h2>Certificates and marksheets</h2>
                </div>
                <span className="result-count">
                  {countLabel(child.certificates.length, 'document')}
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Document</th>
                      <th scope="col">Type</th>
                      <th scope="col">Issued</th>
                      <th scope="col">Result</th>
                      <th scope="col">Verification</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {child.certificates.map((certificate) => {
                      const downloading = downloadingId === certificate.id
                      return (
                        <tr key={certificate.id}>
                          <td>
                            <strong>{certificate.certificate_number}</strong>
                            {!certificate.is_valid && (
                              <span className="revoked-label">Revoked</span>
                            )}
                          </td>
                          <td>{documentLabel(certificate.document_type)}</td>
                          <td>{formatCertificateDate(certificate.issue_date)}</td>
                          <td>
                            {formatCertificateResult(
                              certificate.grade,
                              certificate.percentage,
                            )}
                          </td>
                          <td>
                            <div className="certificate-code-block">
                              <span className="code-pill">
                                {certificate.verification_code}
                              </span>
                              <div className="certificate-code-actions">
                                <CopyButton
                                  value={certificate.verification_code}
                                  label="Copy"
                                />
                                <a
                                  href={certificateVerificationPath(
                                    certificate.verification_code,
                                  )}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Verify
                                </a>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="row-actions document-row-actions">
                              <button
                                onClick={() => setPreview(certificate)}
                                type="button"
                              >
                                View
                              </button>
                              <button
                                disabled={downloading}
                                onClick={() => void download(certificate)}
                                type="button"
                              >
                                {downloading ? 'Preparing…' : 'Download'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {!child.certificates.length && (
                  <div className="table-state">
                    No certificates have been issued for this student yet.
                  </div>
                )}
              </div>
            </div>
          </section>
        ))}
      </div>

      {preview && (
        <CertificatePreviewModal
          key={preview.id}
          certificate={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </main>
  )
}

export default ParentPortalPage
