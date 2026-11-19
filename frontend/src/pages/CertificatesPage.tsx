import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import api from '../services/api'
import CertificatePreviewModal from '../components/CertificatePreviewModal'
import CopyButton from '../components/CopyButton'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser } from '../utils/auth'
import {
  certificateErrorMessage,
  downloadCertificateDocument,
} from '../utils/certificateDocument'
import {
  certificateVerificationPath,
  certificateVerificationUrl,
  copyText,
  countLabel,
  formatCertificateDate,
  formatCertificateResult,
} from '../utils/certificateUi'

type Certificate = {
  id: number
  certificate_number: string
  verification_code: string
  enrollment_id: number
  document_type: string
  issue_date: string
  grade: string | null
  percentage: number | null
  is_valid: boolean
}
type Enrollment = { id: number; student_id: number; batch_id: number; status: string }
type Student = { id: number; full_name: string; student_code: string }
type Batch = { id: number; name: string; code: string }
type BranchDesign = {
  id: number
  name: string
  address: string | null
  phone: string | null
  email: string | null
  certificate_title: string | null
  marksheet_title: string | null
  certificate_primary_color: string
  certificate_accent_color: string
  certificate_template: string | null
  marksheet_template: string | null
}
type Verification = {
  valid: boolean
  certificate_number: string
  document_type: string
  issue_date: string
  student_name: string
  student_code: string
  course_name: string
  branch_name: string
  grade: string | null
  percentage: number | null
}

type Eligibility = {
  enrollment_id: number
  enrollment_status: string
  document_type: string
  student_name: string
  student_code: string
  course_name: string
  course_timing: {
    course_duration_months: number
    course_end_date: string | null
    days_remaining: number | null
    completed: boolean
    met: boolean
    note: string | null
  }
  attendance: {
    recorded_days: number
    present_days: number
    late_days: number
    excused_days: number
    attended_days: number
    percentage: number
    minimum_percentage: number
    met: boolean
    note: string | null
  }
  fees: {
    has_fee_plan: boolean
    total_fee: number | string
    paid_amount: number | string
    outstanding_amount: number | string
    met: boolean
  }
  exams: {
    published_subjects: number
    marked_subjects: number
    all_marks_recorded: boolean
    grade: string | null
    passed: boolean
    met: boolean
  }
  assignments: { tracked: boolean; met: boolean; note: string }
  online_exams: {
    tracked: boolean
    total_exams: number
    passed_exams: number
    met: boolean
    note: string
  }
  eligible: boolean
  blockers: string[]
}

type AutoIssueResult = {
  scanned: number
  completed_enrollments: number
  issued: number
  skipped: number
  dry_run: boolean
  items: {
    enrollment_id: number
    student_name: string
    course_name: string
    course_end_date: string | null
    action: string
    detail: string | null
  }[]
}

function formatMoney(value: number | string | null | undefined): string {
  return `₹${Number(value ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function documentLabel(value: string): string {
  return value === 'certificate' ? 'Certificate' : 'Marksheet'
}

function serializeDesign(design: BranchDesign): string {
  return JSON.stringify([
    design.certificate_title,
    design.marksheet_title,
    design.certificate_primary_color,
    design.certificate_accent_color,
    design.certificate_template,
    design.marksheet_template,
  ])
}

function normalizeHex(value: string): string | null {
  const raw = value.trim().replace(/^#/, '')
  return /^[0-9a-fA-F]{6}$/.test(raw) ? `#${raw.toLowerCase()}` : null
}

const defaultCertificateTemplate = `<div style="font-family: Georgia, serif; text-align: center; border: 8px double {{accent_color}}; padding: 42px; color: {{primary_color}};">
<div style="font-size: 11px; letter-spacing: 3px; color: {{accent_color}};">{{branch_name}}</div>
<h1 style="font-size: 28px; margin: 24px 0 8px; color: {{primary_color}};">{{certificate_title}}</h1>
<p style="font-size: 15px;">This is proudly presented to</p>
<h2 style="font-size: 25px; margin: 12px 0; color: {{primary_color}};">{{student_name}}</h2>
<p>for successfully completing <strong>{{course_name}}</strong></p>
<div style="margin-top: 28px; font-size: 11px;">Issued on {{issue_date}} · Certificate No. {{certificate_number}}</div>
<div style="margin-top: 8px; font-size: 12px; font-style: italic;">{{digital_signature}}</div>
<div style="margin-top: 14px;">{{verification_qr}}</div>
</div>`

const defaultMarksheetTemplate = `<div style="font-family: Arial, sans-serif; border: 3px solid {{primary_color}}; padding: 26px; color: {{primary_color}};">
<div style="text-align: center; color: {{accent_color}}; letter-spacing: 2px;">{{branch_name}}</div>
<h1 style="text-align: center; margin: 20px 0; color: {{primary_color}};">{{marksheet_title}}</h1>
<p><strong>Student:</strong> {{student_name}} &nbsp; <strong>Course:</strong> {{course_name}}</p>
{{marks_table}}
<p style="text-align: right; color: {{primary_color}};">Percentage: {{percentage}} · Grade: {{grade}}</p>
<div style="margin-top: 14px; text-align: right;">
  <span style="font-size: 11px; float: left; margin-top: 10px;">Issued on {{issue_date}} · Certificate No. {{certificate_number}}</span>
  {{verification_qr}}
</div>
</div>`

const PLACEHOLDERS = [
  '{{student_name}}',
  '{{student_code}}',
  '{{course_name}}',
  '{{course_duration}}',
  '{{batch_name}}',
  '{{branch_name}}',
  '{{branch_address}}',
  '{{branch_phone}}',
  '{{branch_email}}',
  '{{issue_date}}',
  '{{admission_date}}',
  '{{certificate_number}}',
  '{{verification_code}}',
  '{{verification_url}}',
  '{{grade}}',
  '{{percentage}}',
  '{{digital_signature}}',
  '{{marks_table}}',
  '{{verification_qr}}',
  '{{document_title}}',
  '{{certificate_title}}',
  '{{marksheet_title}}',
  '{{primary_color}}',
  '{{accent_color}}',
]

const AUTO_ACTION_LABELS: Record<string, string> = {
  issued: 'Issued',
  skipped: 'Skipped',
}

function ColorControl({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const displayed = draft ?? value

  function commit(raw: string) {
    const next = normalizeHex(raw)
    setDraft(null)
    if (next) onChange(next)
  }

  return (
    <div className="color-control">
      <input
        aria-label={`${label} colour picker`}
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="color-copy">
        <strong>{label}</strong>
        <input
          aria-label={`${label} hex colour`}
          className="color-hex"
          value={displayed}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={(event) => commit(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              commit(displayed)
              event.currentTarget.blur()
            }
          }}
          maxLength={7}
          spellCheck={false}
        />
      </div>
    </div>
  )
}

export function CertificateVerificationPage() {
  const [searchParams] = useSearchParams()
  const [code, setCode] = useState('')
  const [result, setResult] = useState<Verification | null>(null)
  const [verifiedCode, setVerifiedCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const autoChecked = useRef(false)

  const runVerify = useCallback(async (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) {
      setError('Enter a verification code.')
      return
    }
    setError('')
    setResult(null)
    setVerifiedCode('')
    setLoading(true)
    try {
      const { data } = await api.get<Verification>(
        `/api/certificates/verify/${encodeURIComponent(trimmed)}`,
      )
      setResult(data)
      setVerifiedCode(trimmed)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Certificate could not be verified.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initial = searchParams.get('code')?.trim()
    if (!initial || autoChecked.current) return
    autoChecked.current = true
    setCode(initial)
    void runVerify(initial)
  }, [runVerify, searchParams])

  function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void runVerify(code)
  }

  return (
    <div className="login-page">
      <div className="login-panel">
        <div className="login-form-wrap">
          <span className="eyebrow">PUBLIC VERIFICATION</span>
          <h2>Verify a certificate</h2>
          <p className="muted">
            Enter the verification code printed on the certificate, or scan the
            QR code on the document.
          </p>
          <form onSubmit={verify}>
            <label htmlFor="verification-code">Verification code</label>
            <input
              id="verification-code"
              value={code}
              onChange={(event) => {
                setCode(event.target.value)
                if (result && event.target.value.trim() !== verifiedCode) {
                  setResult(null)
                  setVerifiedCode('')
                }
              }}
              autoComplete="off"
              required
            />
            <button
              className="primary-button login-button"
              type="submit"
              disabled={loading}
            >
              {loading ? 'Verifying…' : 'Verify certificate'}
            </button>
          </form>
          {error && <div className="form-error">{error}</div>}
          {loading && (
            <div className="table-state verification-loading" aria-live="polite">
              Verifying certificate…
            </div>
          )}
          {result && !loading && (
            <div className="verification-card" aria-live="polite">
              <strong>
                {result.valid
                  ? `Valid ${documentLabel(result.document_type).toLowerCase()}`
                  : `${documentLabel(result.document_type)} is not valid`}
              </strong>
              <p>
                {result.student_name} ({result.student_code})
              </p>
              <p>
                {result.course_name} · {result.branch_name}
              </p>
              <p>
                {documentLabel(result.document_type)} ·{' '}
                {formatCertificateDate(result.issue_date)}
              </p>
              <p>Certificate no. {result.certificate_number}</p>
              <p>Result: {formatCertificateResult(result.grade, result.percentage)}</p>
              <p className="verification-note">
                The certificate holder or institute staff can download the PDF
                from the signed-in portal.
              </p>
              <div className="verification-footer">
                <QRCodeSVG
                  value={certificateVerificationUrl(verifiedCode)}
                  size={64}
                  bgColor="#ffffff"
                  fgColor="#172a43"
                  level="M"
                />
                <div className="verification-footer-copy">
                  <span>
                    Official public verification link. Scan to verify on any
                    mobile device.
                  </span>
                  <div className="code-copy-row">
                    <span className="code-pill">{verifiedCode}</span>
                    <CopyButton value={verifiedCode} label="Copy code" />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CertificatesPage() {
  const [certificates, setCertificates] = useState<Certificate[]>([])
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [students, setStudents] = useState<Student[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [form, setForm] = useState({
    enrollment_id: '',
    document_type: 'certificate',
    digital_signature: '',
    allow_early: false,
  })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [preview, setPreview] = useState<Certificate | null>(null)
  const [loadError, setLoadError] = useState('')
  const [issueError, setIssueError] = useState('')
  const [issueMessage, setIssueMessage] = useState('')
  const [registerError, setRegisterError] = useState('')
  const [registerMessage, setRegisterMessage] = useState('')
  const [eligibility, setEligibility] = useState<Eligibility | null>(null)
  const [eligibilityError, setEligibilityError] = useState('')
  const [eligibilityLoading, setEligibilityLoading] = useState(false)
  const [autoIssueResult, setAutoIssueResult] = useState<AutoIssueResult | null>(null)
  const [autoAction, setAutoAction] = useState<'preview' | 'run' | null>(null)
  const [autoError, setAutoError] = useState('')
  const [confirmAutoRun, setConfirmAutoRun] = useState(false)
  const [branchDesigns, setBranchDesigns] = useState<BranchDesign[]>([])
  const [designSnapshots, setDesignSnapshots] = useState<Record<number, string>>({})
  const [designBranchId, setDesignBranchId] = useState('')
  const [designSaving, setDesignSaving] = useState(false)
  const [designLoading, setDesignLoading] = useState(true)
  const [designError, setDesignError] = useState('')
  const [designMessage, setDesignMessage] = useState('')
  const [designType, setDesignType] = useState<'certificate' | 'marksheet'>('certificate')
  const [promptStatus, setPromptStatus] = useState<'idle' | 'copied' | 'error'>('idle')
  const eligibilityRequest = useRef(0)
  const certificateTabRef = useRef<HTMLButtonElement>(null)
  const marksheetTabRef = useRef<HTMLButtonElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const results = await Promise.allSettled([
        api.get<Certificate[]>('/api/certificates'),
        api.get<Enrollment[]>('/api/enrollments'),
        api.get<Student[]>('/api/students'),
        api.get<Batch[]>('/api/batches'),
      ])
      if (results[0].status === 'fulfilled') setCertificates(results[0].value.data)
      if (results[1].status === 'fulfilled') setEnrollments(results[1].value.data)
      if (results[2].status === 'fulfilled') setStudents(results[2].value.data)
      if (results[3].status === 'fulfilled') setBatches(results[3].value.data)
      const failure = results.find(
        (result): result is PromiseRejectedResult => result.status === 'rejected',
      )
      if (failure) {
        setLoadError(apiErrorMessage(failure.reason, 'Unable to load certificates.'))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const loadBranchDesigns = useCallback(async () => {
    setDesignLoading(true)
    setDesignError('')
    try {
      const { data } = await api.get<BranchDesign[]>('/api/branches')
      setBranchDesigns(data)
      setDesignSnapshots(
        Object.fromEntries(data.map((branch) => [branch.id, serializeDesign(branch)])),
      )
      setDesignBranchId((current) => current || String(data[0]?.id ?? ''))
    } catch (requestError) {
      setDesignError(
        apiErrorMessage(requestError, 'Unable to load certificate design settings.'),
      )
    } finally {
      setDesignLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadBranchDesigns(), 0)
    return () => window.clearTimeout(timer)
  }, [loadBranchDesigns])

  const selectedDesign = branchDesigns.find((branch) => String(branch.id) === designBranchId)
  const designDirty = Boolean(
    selectedDesign && designSnapshots[selectedDesign.id] !== serializeDesign(selectedDesign),
  )

  useEffect(() => {
    if (designDirty) return
    const refresh = () => {
      if (!document.hidden) void loadBranchDesigns()
    }
    const interval = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [designDirty, loadBranchDesigns])

  const designTitle = designType === 'certificate'
    ? selectedDesign?.certificate_title ?? ''
    : selectedDesign?.marksheet_title ?? ''
  const designLabel = designType === 'certificate' ? 'Certificate' : 'Marksheet'
  const designTemplate = designType === 'certificate'
    ? selectedDesign?.certificate_template ?? defaultCertificateTemplate
    : selectedDesign?.marksheet_template ?? defaultMarksheetTemplate
  const verificationPreviewUrl = certificateVerificationUrl('VERIFY-2026-001')
  const primaryColor = selectedDesign?.certificate_primary_color || '#172a43'
  const accentColor = selectedDesign?.certificate_accent_color || '#c19a3d'
  const certTitle = (selectedDesign?.certificate_title || '').trim() || 'CERTIFICATE'
  const marksheetTitle = (selectedDesign?.marksheet_title || '').trim() || 'STATEMENT OF MARKS'
  const currentTitle = designType === 'certificate' ? certTitle : marksheetTitle

  useEffect(() => {
    if (!designDirty) return
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [designDirty])

  let rendered = designTemplate
    .replaceAll('{{branch_name}}', selectedDesign?.name ?? 'NICT Institute')
    .replaceAll('{{branch_address}}', selectedDesign?.address || 'Branch address not set')
    .replaceAll('{{branch_phone}}', selectedDesign?.phone || 'Branch phone not set')
    .replaceAll('{{branch_email}}', selectedDesign?.email || 'Branch email not set')
    .replaceAll('{{student_name}}', 'Student Name')
    .replaceAll('{{student_code}}', 'STD-2026-001')
    .replaceAll('{{course_name}}', 'Professional Web Development')
    .replaceAll('{{course_duration}}', '6 months')
    .replaceAll('{{batch_name}}', 'Morning Batch')
    .replaceAll('{{admission_date}}', '1 June 2026')
    .replaceAll('{{issue_date}}', '4 November 2026')
    .replaceAll('{{certificate_number}}', 'CERT-2026-001')
    .replaceAll('{{verification_code}}', 'VERIFY-2026-001')
    .replaceAll('{{verification_url}}', verificationPreviewUrl)
    .replaceAll('{{grade}}', 'A+')
    .replaceAll('{{percentage}}', '88.5%')
    .replaceAll('{{digital_signature}}', 'Authorised Signatory')
    .replaceAll('{{document_title}}', currentTitle)
    .replaceAll('{{certificate_title}}', certTitle)
    .replaceAll('{{marksheet_title}}', marksheetTitle)
    .replaceAll('{{primary_color}}', primaryColor)
    .replaceAll('{{accent_color}}', accentColor)
    .replaceAll(
      '{{marks_table}}',
      `<table style="width:100%;border-collapse:collapse;margin:16px 0;"><thead><tr style="background:#f3f7fd;"><th style="border:1px solid #dbe3ee;padding:7px;color:${primaryColor};">Exam</th><th style="border:1px solid #dbe3ee;padding:7px;color:${primaryColor};">Subject</th><th style="border:1px solid #dbe3ee;padding:7px;color:${primaryColor};">Marks</th><th style="border:1px solid #dbe3ee;padding:7px;color:${primaryColor};">Maximum</th><th style="border:1px solid #dbe3ee;padding:7px;color:${primaryColor};">Grade</th></tr></thead><tbody><tr><td style="border:1px solid #dbe3ee;padding:7px;">Final Exam</td><td style="border:1px solid #dbe3ee;padding:7px;">Full Stack Web Development</td><td style="border:1px solid #dbe3ee;padding:7px;">88.5</td><td style="border:1px solid #dbe3ee;padding:7px;">100</td><td style="border:1px solid #dbe3ee;padding:7px;font-weight:bold;color:${primaryColor};">A+</td></tr></tbody></table>`
    )
    .replaceAll(
      '{{verification_qr}}',
      `<div style="display:inline-block;border:1px solid #dbe3ee;padding:3px;background:#fff;border-radius:4px;"><div style="width:52px;height:52px;background:#f3f7fd;display:flex;align-items:center;justify-content:center;color:${primaryColor};font-size:9px;font-weight:bold;text-align:center;">QR CODE</div></div>`
    )

  // Immediate live reflection for custom colors even in legacy templates with hardcoded hex colors
  if (primaryColor.toLowerCase() !== '#172a43') {
    rendered = rendered.replaceAll('#172a43', primaryColor).replaceAll('#172A43', primaryColor)
  }
  if (accentColor.toLowerCase() !== '#c19a3d') {
    rendered = rendered.replaceAll('#c19a3d', accentColor).replaceAll('#C19A3D', accentColor)
  }

  // Immediate live reflection for title input if template still contains static <h1>
  if (designType === 'certificate' && selectedDesign?.certificate_title) {
    rendered = rendered.replace(/<h1([^>]*)>CERTIFICATE<\/h1>/i, `<h1$1>${certTitle}</h1>`)
  } else if (designType === 'marksheet' && selectedDesign?.marksheet_title) {
    rendered = rendered.replace(/<h1([^>]*)>STATEMENT OF MARKS<\/h1>/i, `<h1$1>${marksheetTitle}</h1>`)
  }

  const previewTemplate = rendered
  const previewScale = designType === 'certificate' ? 0.78 : 0.68
  const aiPrompt = `Create a polished, print-ready ${designLabel.toLowerCase()} HTML template for an institute management system. Use a premium academic style, strong spacing, clear hierarchy, and an A4-safe layout. Do not use JavaScript, external images, external fonts, external URLs, forms, or animations. Use only inline CSS and these placeholders: ${PLACEHOLDERS.join(', ')}. Include {{verification_qr}} in a neat footer area for certificate verification, the code should be under 12,000 characters, and the template should be responsive for printing. Use {{primary_color}} and {{accent_color}} for the main color scheme. Do not include any other text or instructions in the template.`;

  async function copyAiPrompt() {
    try {
      await copyText(aiPrompt)
      setPromptStatus('copied')
    } catch {
      setPromptStatus('error')
    }
    window.setTimeout(() => setPromptStatus('idle'), 2200)
  }

  const previewDocument = `<!doctype html><html><head><meta charset="utf-8"><style>:root{--primary-color:${primaryColor};--accent-color:${accentColor};}*{box-sizing:border-box;}html,body{margin:0;padding:0;min-height:100%;overflow:auto;background:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:${primaryColor};}body{padding:20px;zoom:${previewScale};}table,th,td{border:1px solid #dbe3ee;padding:6px}th{background:#f3f7fd}</style></head><body>${previewTemplate}</body></html>`

  function updateDesign(changes: Partial<BranchDesign>) {
    if (!selectedDesign) return
    setDesignMessage('')
    setDesignError('')
    setBranchDesigns((current) => current.map((branch) =>
      branch.id === selectedDesign.id ? { ...branch, ...changes } : branch,
    ))
  }

  function resetDesign() {
    if (!window.confirm('Reset this template and its colours to the default? This cannot be undone.')) {
      return
    }
    updateDesign(designType === 'certificate'
      ? { certificate_title: '', certificate_primary_color: '#172a43', certificate_accent_color: '#c19a3d', certificate_template: defaultCertificateTemplate }
      : { marksheet_title: '', certificate_primary_color: '#172a43', certificate_accent_color: '#c19a3d', marksheet_template: defaultMarksheetTemplate })
    setDesignMessage('Template reset locally. Save changes to keep it.')
  }

  async function saveDesign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDesign) return
    setDesignSaving(true)
    setDesignError('')
    setDesignMessage('')
    try {
      const designPayload = {
        certificate_title: selectedDesign.certificate_title || null,
        marksheet_title: selectedDesign.marksheet_title || null,
        certificate_primary_color: selectedDesign.certificate_primary_color,
        certificate_accent_color: selectedDesign.certificate_accent_color,
        certificate_template: selectedDesign.certificate_template || null,
        marksheet_template: selectedDesign.marksheet_template || null,
      }
      const { data } = await api.patch<BranchDesign>(`/api/branches/${selectedDesign.id}`, designPayload)
      setBranchDesigns((current) => current.map((branch) => branch.id === data.id ? { ...branch, ...data } : branch))
      setDesignSnapshots((current) => ({ ...current, [data.id]: serializeDesign(data) }))
      setDesignMessage('Certificate design settings saved.')
    } catch (requestError) {
      setDesignError(apiErrorMessage(requestError, 'Unable to save certificate design settings.'))
    } finally {
      setDesignSaving(false)
    }
  }

  async function checkEligibility(enrollmentId: string, documentType: string) {
    if (!enrollmentId) {
      setEligibility(null)
      setEligibilityError('')
      setEligibilityLoading(false)
      return
    }
    const requestId = eligibilityRequest.current + 1
    eligibilityRequest.current = requestId
    setEligibility(null)
    setEligibilityError('')
    setEligibilityLoading(true)
    try {
      const { data } = await api.get<Eligibility>(
        `/api/certificates/eligibility/${enrollmentId}`,
        { params: { document_type: documentType } },
      )
      if (requestId === eligibilityRequest.current) setEligibility(data)
    } catch (requestError) {
      if (requestId === eligibilityRequest.current) {
        setEligibilityError(
          apiErrorMessage(requestError, 'Unable to check eligibility for this enrollment.'),
        )
      }
    } finally {
      if (requestId === eligibilityRequest.current) setEligibilityLoading(false)
    }
  }

  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setIssueError('')
    setIssueMessage('')
    try {
      await api.post('/api/certificates', {
        enrollment_id: Number(form.enrollment_id),
        document_type: form.document_type,
        digital_signature: form.digital_signature || null,
        allow_early: form.allow_early,
      })
      setForm({
        enrollment_id: '',
        document_type: 'certificate',
        digital_signature: '',
        allow_early: false,
      })
      setEligibility(null)
      setEligibilityError('')
      setIssueMessage('Document issued. You can now preview or download it below.')
      await load()
    } catch (requestError) {
      setIssueError(
        apiErrorMessage(
          requestError,
          'Unable to issue this document. Check enrollment status and published results.',
        ),
      )
    } finally {
      setSaving(false)
    }
  }

  async function download(certificate: Certificate) {
    setDownloadingId(certificate.id)
    setRegisterError('')
    setRegisterMessage('')
    try {
      await downloadCertificateDocument(
        certificate.id,
        certificate.certificate_number,
      )
      setRegisterMessage(`Downloaded ${certificate.certificate_number}.pdf`)
    } catch (requestError) {
      setRegisterError(
        certificateErrorMessage(
          requestError,
          'Unable to download this document. Please try again.',
        ),
      )
    } finally {
      setDownloadingId(null)
    }
  }

  async function runAutoIssue(dryRun: boolean) {
    setAutoAction(dryRun ? 'preview' : 'run')
    setAutoError('')
    setAutoIssueResult(null)
    try {
      const { data } = await api.post<AutoIssueResult>('/api/certificates/auto-issue', {
        document_type: 'certificate',
        dry_run: dryRun,
      })
      setAutoIssueResult(data)
      if (!dryRun) await load()
    } catch (requestError) {
      setAutoError(apiErrorMessage(requestError, 'Unable to run automatic certificate generation.'))
    } finally {
      setAutoAction(null)
    }
  }

  function requestAutoRun() {
    if (autoAction) return
    setConfirmAutoRun(true)
  }

  function selectDesignType(next: 'certificate' | 'marksheet') {
    setDesignType(next)
  }

  function handleDesignerTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    let next: 'certificate' | 'marksheet'
    if (event.key === 'Home') next = 'certificate'
    else if (event.key === 'End') next = 'marksheet'
    else next = designType === 'certificate' ? 'marksheet' : 'certificate'
    setDesignType(next)
    const target = next === 'certificate' ? certificateTabRef : marksheetTabRef
    target.current?.focus()
  }

  function handleDesignBranchChange(nextId: string) {
    if (designDirty && !window.confirm('You have unsaved design changes. Switch branch anyway?')) {
      return
    }
    setDesignBranchId(nextId)
    setDesignError('')
    setDesignMessage('')
  }

  const studentName = (id: number) =>
    students.find((student) => student.id === id)?.full_name ?? `Student #${id}`
  const batchName = (id: number) =>
    batches.find((batch) => batch.id === id)?.name ?? `Batch #${id}`
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role_name === 'Super Admin'
  const canManageDesign = ['Super Admin', 'Branch Admin', 'Staff'].includes(
    currentUser?.role_name ?? '',
  )
  const canAutoIssue = ['Super Admin', 'Branch Admin'].includes(
    currentUser?.role_name ?? '',
  )
  const earlyOverride = isSuperAdmin && form.allow_early
  const issueDisabled =
    saving ||
    eligibilityLoading ||
    !eligibility ||
    (!eligibility.eligible && !earlyOverride)

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">DOCUMENTS</span>
          <h1>Certificates</h1>
          <p>
            Issue certificates and marksheets, preview them, and download
            print-ready PDFs.
          </p>
        </div>
      </div>

      {loadError && <div className="inline-error">{loadError}</div>}

      {canManageDesign && (
        <section className="data-panel settings-card">
          <div className="section-title">
            <div>
              <span className="eyebrow">DOCUMENT DESIGN</span>
              <h2>Certificate and marksheet format</h2>
              <p className="muted">One shared format for every authorised role in the selected branch. Changes are saved centrally and appear for Super Admin, Branch Admin, and Staff.</p>
            </div>
            {designDirty && (
              <span className="designer-dirty" aria-live="polite">Unsaved changes</span>
            )}
          </div>

          {designLoading ? (
            <div className="table-state">Loading certificate designs…</div>
          ) : !selectedDesign ? (
            <div className="table-state">
              <strong>Design settings unavailable</strong>
              <p>{designError || 'No branch is available for certificate design.'}</p>
              {designError && (
                <button className="secondary-button" onClick={() => void loadBranchDesigns()} type="button">
                  Try again
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="designer-tabs" role="tablist" aria-label="Document type">
                <button
                  type="button"
                  id="designer-tab-certificate"
                  className={designType === 'certificate' ? 'designer-tab active' : 'designer-tab'}
                  onClick={() => selectDesignType('certificate')}
                  role="tab"
                  aria-selected={designType === 'certificate'}
                  aria-controls="designer-panel"
                  tabIndex={designType === 'certificate' ? 0 : -1}
                  ref={certificateTabRef}
                  onKeyDown={handleDesignerTabKeyDown}
                >
                  <strong>Certificate</strong>
                  <small>Course completion</small>
                </button>
                <button
                  type="button"
                  id="designer-tab-marksheet"
                  className={designType === 'marksheet' ? 'designer-tab active' : 'designer-tab'}
                  onClick={() => selectDesignType('marksheet')}
                  role="tab"
                  aria-selected={designType === 'marksheet'}
                  aria-controls="designer-panel"
                  tabIndex={designType === 'marksheet' ? 0 : -1}
                  ref={marksheetTabRef}
                  onKeyDown={handleDesignerTabKeyDown}
                >
                  <strong>Marksheet</strong>
                  <small>Academic results</small>
                </button>
              </div>
              <div
                className="designer-workspace"
                id="designer-panel"
                role="tabpanel"
                aria-labelledby={designType === 'certificate' ? 'designer-tab-certificate' : 'designer-tab-marksheet'}
                tabIndex={0}
              >
                <form className="designer-controls" onSubmit={saveDesign}>
                  {branchDesigns.length > 1 && (
                    <div className="field">
                      <label htmlFor="design-branch-new">Editing branch</label>
                      <select
                        id="design-branch-new"
                        value={designBranchId}
                        onChange={(event) => handleDesignBranchChange(event.target.value)}
                      >
                        {branchDesigns.map((branch) => (
                          <option key={branch.id} value={branch.id}>{branch.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="designer-step"><span>1</span><div><strong>Document title</strong><small>This is shown at the top of the {designLabel.toLowerCase()}.</small></div></div>
                  <div className="field"><label htmlFor="design-title">{designLabel} title</label><input id="design-title" value={designTitle} onChange={(event) => updateDesign(designType === 'certificate' ? { certificate_title: event.target.value } : { marksheet_title: event.target.value })} placeholder={designType === 'certificate' ? 'CERTIFICATE' : 'STATEMENT OF MARKS'} maxLength={180} /></div>
                  <div className="designer-step"><span>2</span><div><strong>Brand colours</strong><small>Pick colours that match your institute identity, or paste a hex value.</small></div></div>
                  <div className="designer-colors">
                    <ColorControl
                      label="Primary"
                      value={selectedDesign.certificate_primary_color}
                      onChange={(value) => updateDesign({ certificate_primary_color: value })}
                    />
                    <ColorControl
                      label="Accent"
                      value={selectedDesign.certificate_accent_color}
                      onChange={(value) => updateDesign({ certificate_accent_color: value })}
                    />
                  </div>
                  <div className="designer-step"><span>3</span><div><strong>Advanced HTML template</strong><small>Use approved placeholders to control the document layout. Scripts and external resources are blocked.</small></div></div>
                  <div className="field">
                    <label htmlFor="design-template">{designLabel} HTML</label>
                    <textarea className="template-editor" id="design-template" value={designTemplate} onChange={(event) => updateDesign(designType === 'certificate' ? { certificate_template: event.target.value } : { marksheet_template: event.target.value })} spellCheck={false} rows={12} />
                    <div className="placeholder-group">
                      <span className="field-hint">Available placeholders</span>
                      <div className="placeholder-grid">
                        {PLACEHOLDERS.map((placeholder) => (
                          <code className="placeholder-chip" key={placeholder}>{placeholder}</code>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="ai-prompt-card">
                    <div>
                      <span className="eyebrow">AI DESIGN ASSISTANT</span>
                      <strong>Generate a starting template with AI</strong>
                      <small>Copy this ready-to-use prompt into ChatGPT, Copilot, or another AI tool, then paste the returned HTML above.</small>
                    </div>
                    <textarea className="ai-prompt" value={aiPrompt} readOnly rows={5} />
                    <button className="secondary-button" onClick={() => void copyAiPrompt()} type="button">
                      {promptStatus === 'copied' ? 'Prompt copied' : promptStatus === 'error' ? 'Copy failed — select the prompt' : 'Copy AI prompt'}
                    </button>
                  </div>
                  {designError && <div className="inline-error designer-feedback">{designError}</div>}
                  {designMessage && <div className="success-message designer-feedback">{designMessage}</div>}
                  <div className="designer-actions">
                    <button className="text-button" onClick={resetDesign} type="button">Reset template</button>
                    <button className="primary-button" disabled={designSaving || !designDirty} type="submit">
                      {designSaving ? 'Saving…' : 'Save changes'}
                    </button>
                  </div>
                </form>
                <div className="designer-preview-panel">
                  <div className="designer-preview-header">
                    <div className="live-sync-badge">
                      <span className="live-sync-dot" />
                      <span>LIVE PREVIEW</span>
                    </div>
                    <div className="preview-meta-tags">
                      <span className="preview-format-pill">
                        {designType === 'certificate' ? 'A4 Landscape (297×210 mm)' : 'A4 Portrait (210×297 mm)'}
                      </span>
                      <span className="preview-branch-pill">
                        {selectedDesign.name}
                      </span>
                    </div>
                  </div>
                  <div className={`template-preview-shell ${designType === 'certificate' ? 'certificate-preview-shell' : 'marksheet-preview-shell'}`}>
                    <iframe className="template-preview-frame" title={`${designLabel} live preview`} sandbox="" scrolling="auto" srcDoc={previewDocument} />
                  </div>
                  <div className="designer-preview-footer">
                    <div className="preview-palette-pills">
                      <span className="palette-pill">
                        <i style={{ backgroundColor: primaryColor }} />
                        Primary: {primaryColor.toUpperCase()}
                      </span>
                      <span className="palette-pill">
                        <i style={{ backgroundColor: accentColor }} />
                        Accent: {accentColor.toUpperCase()}
                      </span>
                    </div>
                    <div className="preview-qr-box">
                      <QRCodeSVG value={verificationPreviewUrl} size={36} bgColor="#ffffff" fgColor={primaryColor} level="M" />
                      <div>
                        <strong>Live Verify QR</strong>
                        <small>Test on mobile</small>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {canAutoIssue && (
        <section className="data-panel settings-card">
          <div className="section-title">
            <div>
              <span className="eyebrow">END OF COURSE</span>
              <h2>Automatic certificate generation</h2>
              <p className="muted">
                Courses that have reached their end date are marked completed,
                and certificates are issued for students who meet attendance,
                fee and exam requirements. Safe to run repeatedly.
              </p>
            </div>
          </div>
          <div className="row-actions">
            <button
              className="secondary-button"
              disabled={autoAction !== null}
              onClick={() => void runAutoIssue(true)}
              type="button"
            >
              {autoAction === 'preview' ? 'Checking…' : 'Preview eligible students'}
            </button>
            <button
              className="primary-button"
              disabled={autoAction !== null}
              onClick={requestAutoRun}
              type="button"
            >
              {autoAction === 'run' ? 'Running…' : 'Run auto-generation'}
            </button>
          </div>
          {confirmAutoRun && (
            <div className="confirm-panel" role="alertdialog" aria-labelledby="auto-run-title">
              <div>
                <strong id="auto-run-title">Issue certificates now?</strong>
                <p>This will mark finished courses completed and issue every eligible certificate. Preview first if you are unsure.</p>
              </div>
              <div className="confirm-actions">
                <button className="secondary-button" onClick={() => setConfirmAutoRun(false)} type="button">Cancel</button>
                <button
                  className="primary-button"
                  onClick={() => {
                    setConfirmAutoRun(false)
                    void runAutoIssue(false)
                  }}
                  type="button"
                >
                  Yes, issue certificates
                </button>
              </div>
            </div>
          )}
          {autoError && <div className="inline-error auto-issue-feedback">{autoError}</div>}
          {autoIssueResult && (
            <div className="auto-issue-summary">
              <div className="auto-issue-metrics">
                <span><strong>{autoIssueResult.scanned}</strong> scanned</span>
                <span><strong>{autoIssueResult.completed_enrollments}</strong> completed</span>
                <span><strong>{autoIssueResult.issued}</strong> issued</span>
                <span><strong>{autoIssueResult.skipped}</strong> skipped</span>
              </div>
              <span className={`auto-issue-badge ${autoIssueResult.dry_run ? 'dry-run' : 'live'}`}>
                {autoIssueResult.dry_run ? 'Dry run — no changes saved' : 'Live run'}
              </span>
            </div>
          )}
          {autoIssueResult && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Student</th>
                    <th scope="col">Course</th>
                    <th scope="col">Course end</th>
                    <th scope="col">Action</th>
                    <th scope="col">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {autoIssueResult.items.map((item) => (
                    <tr key={item.enrollment_id}>
                      <td>{item.student_name}</td>
                      <td>{item.course_name}</td>
                      <td>{formatCertificateDate(item.course_end_date)}</td>
                      <td>
                        <span className={`auto-action-pill ${item.action}`}>
                          {AUTO_ACTION_LABELS[item.action] ?? item.action}
                        </span>
                      </td>
                      <td>{item.detail ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!autoIssueResult.items.length && (
                <div className="table-state">
                  No course has reached its end date yet.
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <section className="data-panel settings-card">
        <div className="section-title">
          <div>
            <span className="eyebrow">ISSUE DOCUMENT</span>
            <h2>Create certificate or marksheet</h2>
          </div>
        </div>
        <form className="settings-form" onSubmit={issue}>
          <div className="field">
            <label htmlFor="certificate-enrollment">Enrollment</label>
            <select
              id="certificate-enrollment"
              value={form.enrollment_id}
              onChange={(event) => {
                setForm({ ...form, enrollment_id: event.target.value, allow_early: false })
                void checkEligibility(event.target.value, form.document_type)
              }}
              required
            >
              <option value="">Select enrollment</option>
              {enrollments
                .filter((item) => item.status !== 'cancelled')
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {studentName(item.student_id)} · {batchName(item.batch_id)}
                  </option>
                ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="certificate-type">Document type</label>
            <select
              id="certificate-type"
              value={form.document_type}
              onChange={(event) => {
                setForm({ ...form, document_type: event.target.value, allow_early: false })
                void checkEligibility(form.enrollment_id, event.target.value)
              }}
            >
              <option value="certificate">Certificate</option>
              <option value="marksheet">Marksheet</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="certificate-signature">Signature or issuer name</label>
            <input
              id="certificate-signature"
              value={form.digital_signature}
              onChange={(event) =>
                setForm({ ...form, digital_signature: event.target.value })
              }
            />
          </div>

          {eligibilityLoading && (
            <div className="table-state eligibility-loading">Checking eligibility…</div>
          )}

          {!eligibilityLoading && eligibilityError && (
            <div className="inline-error eligibility-error" role="alert">
              {eligibilityError}
              <button
                className="secondary-button"
                onClick={() => void checkEligibility(form.enrollment_id, form.document_type)}
                type="button"
              >
                Retry check
              </button>
            </div>
          )}

          {!eligibilityLoading && eligibility && (
            <div
              className={`eligibility-card ${
                eligibility.eligible ? 'eligible' : 'blocked'
              }`}
            >
              <div className="eligibility-head">
                <strong>
                  {eligibility.eligible ? 'Eligible to issue' : 'Not eligible yet'}
                </strong>
                <span>
                  {eligibility.student_name} · {eligibility.course_name} ·{' '}
                  {eligibility.enrollment_status}
                </span>
              </div>
              <div className="eligibility-checks">
                <div className={eligibility.course_timing.met ? 'check ok' : 'check fail'}>
                  <span>Course duration</span>
                  <strong>
                    {eligibility.course_timing.course_end_date
                      ? eligibility.course_timing.completed
                        ? 'Completed'
                        : `${eligibility.course_timing.days_remaining}d left`
                      : 'Not set'}
                  </strong>
                  <small>
                    {eligibility.course_timing.course_end_date
                      ? `Ends ${formatCertificateDate(eligibility.course_timing.course_end_date)} · ${eligibility.course_timing.course_duration_months} months`
                      : eligibility.course_timing.note}
                  </small>
                </div>
                <div className={eligibility.attendance.met ? 'check ok' : 'check fail'}>
                  <span>Attendance</span>
                  <strong>
                    {eligibility.attendance.recorded_days > 0
                      ? `${eligibility.attendance.percentage}%`
                      : 'No data'}
                  </strong>
                  <small>Required {eligibility.attendance.minimum_percentage}%</small>
                </div>
                <div className={eligibility.fees.met ? 'check ok' : 'check fail'}>
                  <span>Fees</span>
                  <strong>
                    {eligibility.fees.has_fee_plan
                      ? eligibility.fees.outstanding_amount &&
                        Number(eligibility.fees.outstanding_amount) > 0
                        ? formatMoney(eligibility.fees.outstanding_amount)
                        : 'Cleared'
                      : 'No plan'}
                  </strong>
                  <small>
                    Paid {formatMoney(eligibility.fees.paid_amount)} of{' '}
                    {formatMoney(eligibility.fees.total_fee)}
                  </small>
                </div>
                <div className={eligibility.exams.met ? 'check ok' : 'check fail'}>
                  <span>Exams</span>
                  <strong>{formatCertificateResult(eligibility.exams.grade, null)}</strong>
                  <small>
                    {eligibility.exams.marked_subjects}/
                    {eligibility.exams.published_subjects} subjects marked
                  </small>
                </div>
                <div className={eligibility.assignments.met ? 'check ok' : 'check fail'}>
                  <span>Assignments</span>
                  <strong>
                    {eligibility.assignments.tracked
                      ? eligibility.assignments.met
                        ? 'Submitted'
                        : 'Pending'
                      : 'Not tracked'}
                  </strong>
                  <small>{eligibility.assignments.note}</small>
                </div>
                <div className={eligibility.online_exams.met ? 'check ok' : 'check fail'}>
                  <span>Online exams</span>
                  <strong>
                    {eligibility.online_exams.tracked
                      ? eligibility.online_exams.met
                        ? 'Passed'
                        : 'Pending'
                      : 'Not tracked'}
                  </strong>
                  <small>{eligibility.online_exams.note}</small>
                </div>
              </div>
              {eligibility.blockers.length > 0 && (
                <ul className="eligibility-blockers">
                  {eligibility.blockers.map((blocker) => (
                    <li key={blocker}>{blocker}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {isSuperAdmin &&
            eligibility &&
            !eligibility.eligible &&
            !eligibility.course_timing.completed && (
              <div className="early-override-panel">
                <label className="checkbox-label" htmlFor="certificate-early-override">
                  <input
                    id="certificate-early-override"
                    type="checkbox"
                    checked={form.allow_early}
                    onChange={(event) =>
                      setForm({ ...form, allow_early: event.target.checked })
                    }
                  />
                  <span>Issue early (Super Admin override)</span>
                </label>
                <small>
                  Only course timing is bypassed. Attendance, fee, exam, and
                  assignment requirements must still be met.
                </small>
              </div>
            )}

          {issueError && <div className="inline-error issue-feedback" role="alert">{issueError}</div>}
          {issueMessage && <div className="success-message issue-feedback">{issueMessage}</div>}

          <button
            className="primary-button"
            disabled={issueDisabled}
            type="submit"
          >
            {saving ? 'Issuing…' : 'Issue document'}
          </button>
        </form>
      </section>

      <section className="data-panel responsibility-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">ISSUED DOCUMENTS</span>
            <h2>Certificate register</h2>
          </div>
          <span className="result-count">{countLabel(certificates.length, 'document')}</span>
        </div>
        {registerError && <div className="inline-error register-feedback" role="alert">{registerError}</div>}
        {registerMessage && <div className="success-message register-feedback">{registerMessage}</div>}
        {loading ? (
          <div className="table-state">Loading issued documents…</div>
        ) : (
          <div className="table-wrap">
            <table className="certificate-register-table">
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Student</th>
                  <th scope="col">Type</th>
                  <th scope="col">Issue date</th>
                  <th scope="col">Result</th>
                  <th scope="col">Verification &amp; QR</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {certificates.map((certificate) => {
                  const enrollment = enrollments.find(
                    (item) => item.id === certificate.enrollment_id,
                  )
                  const downloading = downloadingId === certificate.id
                  return (
                    <tr key={certificate.id}>
                      <td>
                        <strong>{certificate.certificate_number}</strong>
                        {!certificate.is_valid && (
                          <span className="revoked-label">Revoked</span>
                        )}
                      </td>
                      <td>
                        {enrollment
                          ? studentName(enrollment.student_id)
                          : '—'}
                      </td>
                      <td>{documentLabel(certificate.document_type)}</td>
                      <td>{formatCertificateDate(certificate.issue_date)}</td>
                      <td>{formatCertificateResult(certificate.grade, certificate.percentage)}</td>
                      <td>
                        <div className="certificate-verify-cell">
                          <QRCodeSVG
                            value={certificateVerificationUrl(certificate.verification_code)}
                            size={64}
                            bgColor="#ffffff"
                            fgColor="#172a43"
                            level="M"
                          />
                          <div className="certificate-code-block">
                            <span className="code-pill">{certificate.verification_code}</span>
                            <div className="certificate-code-actions">
                              <CopyButton value={certificate.verification_code} label="Copy" />
                              <a
                                href={certificateVerificationPath(certificate.verification_code)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Verify
                              </a>
                            </div>
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
            {!certificates.length && !loadError && (
              <div className="table-state">
                No certificates or marksheets issued yet.
              </div>
            )}
          </div>
        )}
      </section>

      {preview && (
        <CertificatePreviewModal
          key={preview.id}
          certificate={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </>
  )
}

export default CertificatesPage
