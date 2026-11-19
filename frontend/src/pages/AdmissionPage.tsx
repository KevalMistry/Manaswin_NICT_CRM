import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'

type Branch = {
  id: number
  name: string
  code: string
  address: string | null
  phone: string | null
  email: string | null
  gstin: string | null
}

type Course = {
  id: number
  name: string
  code: string
  duration_months: number
  fee_amount: string | null
  registration_fee: string
}

type Catalog = {
  branches: Branch[]
  courses: Course[]
  payment_provider: string
  payment_currency: string
  gst_rate_percent: number
}

type CreatedApplication = {
  application_id: number
  application_code: string
  upload_token: string
  status: string
  payment_status: string
  registration_fee: string
  course_name: string
  branch_name: string
  message: string
}

type AdmissionDocument = {
  id: number
  document_type: string
  title: string
  file_name: string
  content_type: string | null
  file_size: number
  uploaded_at: string
  download_url: string
}

type AdmissionPayment = {
  amount: string
  status: string
  payment_method: string
  provider: string
  reference: string | null
  invoice_number: string | null
  paid_at: string | null
  created_at: string
}

type ApplicationStatus = {
  application_code: string
  full_name: string
  email: string | null
  phone: string
  branch_name: string
  course_name: string
  status: string
  payment_status: string
  registration_fee: string
  total_paid: string
  documents: AdmissionDocument[]
  payments: AdmissionPayment[]
  student_code: string | null
  roll_number: string | null
  enrollment_code: string | null
  rejection_reason: string | null
  created_at: string
}

type PaymentIntent = {
  provider: string
  status: string
  payment_status: string
  amount: string
  currency: string
  order_id: string | null
  key_id: string | null
  instructions: string
}

type RazorpayResponse = {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

const DOCUMENT_TYPES = [
  { value: 'aadhaar', label: 'Aadhaar card' },
  { value: 'pan', label: 'PAN card' },
  { value: 'photo', label: 'Photograph' },
  { value: 'marksheet', label: 'Marksheet' },
  { value: 'certificate', label: 'Certificate' },
  { value: 'id_proof', label: 'ID proof' },
  { value: 'other', label: 'Other document' },
]

const STATUS_LABELS: Record<string, string> = {
  submitted: 'Submitted',
  under_review: 'Under review',
  approved: 'Approved',
  rejected: 'Rejected',
  enrolled: 'Enrolled',
  withdrawn: 'Withdrawn',
  unpaid: 'Unpaid',
  pending: 'Pending',
  paid: 'Paid',
  refunded: 'Refunded',
}

const EMPTY_FORM = {
  full_name: '',
  email: '',
  phone: '',
  date_of_birth: '',
  gender: '',
  parent_name: '',
  parent_phone: '',
  qualification: '',
  address: '',
  branch_id: '',
  course_id: '',
  notes: '',
}

function inr(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '₹0'
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function label(value: string): string {
  return STATUS_LABELS[value] ?? value.replaceAll('_', ' ')
}

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    const existing = (window as unknown as { Razorpay?: unknown }).Razorpay
    if (existing) {
      resolve(true)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

function AdmissionPage() {
  const saved = useMemo(() => {
    try {
      const raw = localStorage.getItem('nict_admission_track')
      return raw ? (JSON.parse(raw) as { code?: string; token?: string }) : {}
    } catch {
      return {}
    }
  }, [])

  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'apply' | 'track'>('apply')
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [created, setCreated] = useState<CreatedApplication | null>(null)
  const [trackCode, setTrackCode] = useState(saved.code ?? '')
  const [trackToken, setTrackToken] = useState(saved.token ?? '')
  const [tracking, setTracking] = useState(false)
  const [trackError, setTrackError] = useState('')
  const [statusData, setStatusData] = useState<ApplicationStatus | null>(null)
  const [uploadType, setUploadType] = useState('aadhaar')
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')
  const [paymentIntent, setPaymentIntent] = useState<PaymentIntent | null>(null)
  const [paymentBusy, setPaymentBusy] = useState(false)
  const [paymentError, setPaymentError] = useState('')

  useEffect(() => {
    let active = true
    api.get<Catalog>('/api/public/admissions/catalog')
      .then(({ data }) => {
        if (!active) return
        setCatalog(data)
        setForm((current) => ({
          ...current,
          branch_id: current.branch_id || String(data.branches[0]?.id ?? ''),
          course_id: current.course_id || String(data.courses[0]?.id ?? ''),
        }))
      })
      .catch((requestError) => {
        if (active) setError(apiErrorMessage(requestError, 'Unable to load the admission form. Please try again.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (saved.code && saved.token) void loadStatus(saved.code, saved.token)
    // The saved values only initialise the tracker once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectedBranch = catalog?.branches.find((branch) => String(branch.id) === form.branch_id)
  const selectedCourse = catalog?.courses.find((course) => String(course.id) === form.course_id)

  function remember(code: string, token: string) {
    localStorage.setItem('nict_admission_track', JSON.stringify({ code, token }))
  }

  async function loadStatus(code = trackCode, token = trackToken) {
    const cleanCode = code.trim()
    const cleanToken = token.trim()
    if (!cleanCode || !cleanToken) {
      setTrackError('Enter both the application code and the access token.')
      return
    }
    setTracking(true)
    setTrackError('')
    try {
      const { data } = await api.get<ApplicationStatus>(
        `/api/public/admissions/${encodeURIComponent(cleanCode)}`,
        { params: { token: cleanToken } },
      )
      setStatusData(data)
      setTrackCode(cleanCode)
      setTrackToken(cleanToken)
      remember(cleanCode, cleanToken)
    } catch (requestError) {
      setStatusData(null)
      setTrackError(apiErrorMessage(requestError, 'Unable to find this application. Check the code and token.'))
    } finally {
      setTracking(false)
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const payload = {
        full_name: form.full_name,
        email: form.email || null,
        phone: form.phone,
        date_of_birth: form.date_of_birth || null,
        gender: form.gender || null,
        parent_name: form.parent_name || null,
        parent_phone: form.parent_phone || null,
        qualification: form.qualification || null,
        address: form.address || null,
        branch_id: Number(form.branch_id),
        course_id: Number(form.course_id),
        notes: form.notes || null,
      }
      const { data } = await api.post<CreatedApplication>('/api/public/admissions', payload)
      if (photoFile) {
        const body = new FormData()
        body.append('file', photoFile)
        body.append('document_type', 'photo')
        body.append('title', 'Photograph')
        await api.post(`/api/public/admissions/${encodeURIComponent(data.application_code)}/documents`, body, {
          params: { token: data.upload_token },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
      setCreated(data)
      setTrackCode(data.application_code)
      setTrackToken(data.upload_token)
      setForm(EMPTY_FORM)
      setPhotoFile(null)
      setTab('track')
      await loadStatus(data.application_code, data.upload_token)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to submit your application. Please check the form and try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!uploadFile || !statusData) {
      setUploadMessage('Choose a file to upload.')
      return
    }
    setUploading(true)
    setUploadMessage('')
    const body = new FormData()
    body.append('file', uploadFile)
    body.append('document_type', uploadType)
    body.append('title', uploadTitle)
    try {
      await api.post(
        `/api/public/admissions/${encodeURIComponent(statusData.application_code)}/documents`,
        body,
        {
          params: { token: trackToken },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )
      setUploadFile(null)
      setUploadTitle('')
      setUploadMessage('Document uploaded successfully.')
      const fileInput = document.getElementById('admission-document-file') as HTMLInputElement | null
      if (fileInput) fileInput.value = ''
      await loadStatus()
    } catch (requestError) {
      setUploadMessage(apiErrorMessage(requestError, 'Unable to upload this document.'))
    } finally {
      setUploading(false)
    }
  }

  async function startPayment() {
    if (!statusData) return
    setPaymentBusy(true)
    setPaymentError('')
    try {
      const { data } = await api.post<PaymentIntent>(
        `/api/public/admissions/${encodeURIComponent(statusData.application_code)}/payment-intent`,
        null,
        { params: { token: trackToken } },
      )
      setPaymentIntent(data)
      if (data.provider === 'razorpay' && data.order_id && data.key_id) {
        const ready = await loadRazorpayScript()
        if (!ready) {
          setPaymentError('Unable to open the secure checkout. Please try again or pay at the branch.')
          return
        }
        const Razorpay = (window as unknown as {
          Razorpay: new (options: Record<string, unknown>) => { open: () => void }
        }).Razorpay
        const checkout = new Razorpay({
          key: data.key_id,
          amount: Math.round(Number(data.amount) * 100),
          currency: data.currency,
          name: 'NICT',
          description: 'Admission registration fee',
          order_id: data.order_id,
          prefill: {
            name: statusData.full_name,
            email: statusData.email ?? undefined,
            contact: statusData.phone,
          },
          handler: async (response: RazorpayResponse) => {
            try {
              await api.post(
                `/api/public/admissions/${encodeURIComponent(statusData.application_code)}/payment/verify`,
                {
                  order_id: response.razorpay_order_id,
                  payment_id: response.razorpay_payment_id,
                  signature: response.razorpay_signature,
                },
                { params: { token: trackToken } },
              )
              await loadStatus()
            } catch (requestError) {
              setPaymentError(apiErrorMessage(requestError, 'Payment verification failed. Contact the institute.'))
            }
          },
        })
        checkout.open()
      }
      await loadStatus()
    } catch (requestError) {
      setPaymentError(apiErrorMessage(requestError, 'Unable to start the payment.'))
    } finally {
      setPaymentBusy(false)
    }
  }

  async function copy(value: string, success: string) {
    try {
      await navigator.clipboard.writeText(value)
      setUploadMessage(success)
    } catch {
      setUploadMessage('Copy the value manually from the field above.')
    }
  }

  const canUpload = statusData && ['submitted', 'under_review'].includes(statusData.status)
  const canPay =
    statusData &&
    Number(statusData.registration_fee) > 0 &&
    !['paid', 'refunded'].includes(statusData.payment_status) &&
    !['rejected', 'withdrawn'].includes(statusData.status)

  return (
    <div className="admission-page">
      <header className="admission-topbar">
        <a className="admission-brand" href="/login">
          <span className="brand-mark">N</span>
          <span><strong>NICT</strong><small>Institute OS</small></span>
        </a>
        <div className="admission-topbar-actions">
          <a className="admission-link" href="/verify-certificate">Verify certificate</a>
          <a className="admission-link" href="/login">Staff sign in</a>
        </div>
      </header>

      <main className="admission-wrap">
        <section className="admission-hero">
          <span className="eyebrow">ADMISSIONS OPEN</span>
          <h1>Start your next chapter at NICT.</h1>
          <p>
            Apply online in a few minutes. Upload your documents, track your application,
            and pay the registration fee at the branch or online.
          </p>
          <div className="admission-hero-chips">
            <span>3, 4 and 6-month programs</span>
            <span>Certificate on completion</span>
            <span>Secure document upload</span>
          </div>
        </section>

        <div className="admission-tabs" role="tablist" aria-label="Admission steps">
          <button
            aria-selected={tab === 'apply'}
            className={tab === 'apply' ? 'active-tab' : ''}
            onClick={() => setTab('apply')}
            role="tab"
            type="button"
          >
            Apply now
          </button>
          <button
            aria-selected={tab === 'track'}
            className={tab === 'track' ? 'active-tab' : ''}
            onClick={() => setTab('track')}
            role="tab"
            type="button"
          >
            Track application
          </button>
        </div>

        {error && <div className="inline-error">{error}</div>}

        {tab === 'apply' && (
          <section className="admission-layout">
            <div className="admission-card">
              <div className="admission-card-heading">
                <span className="eyebrow">APPLICATION FORM</span>
                <h2>Tell us about you</h2>
                <p>Fields marked * are required. You can upload documents after submitting.</p>
              </div>
              {loading ? (
                <div className="table-state">Loading programs…</div>
              ) : (
                <form onSubmit={submit} className="admission-form">
                  <div className="admission-form-grid">
                    <div className="field">
                      <label htmlFor="admission-name">Full name *</label>
                      <input
                        id="admission-name"
                        value={form.full_name}
                        onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                        autoComplete="name"
                        required
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-phone">Mobile number *</label>
                      <input
                        id="admission-phone"
                        type="tel"
                        value={form.phone}
                        onChange={(event) => setForm({ ...form, phone: event.target.value })}
                        autoComplete="tel"
                        required
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-email">Email address</label>
                      <input
                        id="admission-email"
                        type="email"
                        value={form.email}
                        onChange={(event) => setForm({ ...form, email: event.target.value })}
                        autoComplete="email"
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-dob">Date of birth</label>
                      <input
                        id="admission-dob"
                        type="date"
                        value={form.date_of_birth}
                        onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-branch">Branch *</label>
                      <select
                        id="admission-branch"
                        value={form.branch_id}
                        onChange={(event) => setForm({ ...form, branch_id: event.target.value })}
                        required
                      >
                        <option value="">Select branch</option>
                        {catalog?.branches.map((branch) => (
                          <option key={branch.id} value={branch.id}>{branch.name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="admission-course">Course *</label>
                      <select
                        id="admission-course"
                        value={form.course_id}
                        onChange={(event) => setForm({ ...form, course_id: event.target.value })}
                        required
                      >
                        <option value="">Select course</option>
                        {catalog?.courses.map((course) => (
                          <option key={course.id} value={course.id}>
                            {course.name} · {course.duration_months} months
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="admission-gender">Gender</label>
                      <select
                        id="admission-gender"
                        value={form.gender}
                        onChange={(event) => setForm({ ...form, gender: event.target.value })}
                      >
                        <option value="">Prefer not to say</option>
                        <option value="Female">Female</option>
                        <option value="Male">Male</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="admission-qualification">Highest qualification</label>
                      <input
                        id="admission-qualification"
                        value={form.qualification}
                        onChange={(event) => setForm({ ...form, qualification: event.target.value })}
                        placeholder="e.g. B.Com, 12th pass"
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-photo">Photograph</label>
                      <input
                        id="admission-photo"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        onChange={(event) => setPhotoFile(event.target.files?.[0] ?? null)}
                      />
                      <small className="field-hint">JPG, PNG or WebP, up to 3 MB.</small>
                    </div>
                    <div className="field">
                      <label htmlFor="admission-parent">Parent / guardian name</label>
                      <input
                        id="admission-parent"
                        value={form.parent_name}
                        onChange={(event) => setForm({ ...form, parent_name: event.target.value })}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="admission-parent-phone">Parent / guardian mobile</label>
                      <input
                        id="admission-parent-phone"
                        type="tel"
                        value={form.parent_phone}
                        onChange={(event) => setForm({ ...form, parent_phone: event.target.value })}
                      />
                    </div>
                    <div className="field full-field">
                      <label htmlFor="admission-address">Address</label>
                      <textarea
                        id="admission-address"
                        rows={2}
                        value={form.address}
                        onChange={(event) => setForm({ ...form, address: event.target.value })}
                      />
                    </div>
                    <div className="field full-field">
                      <label htmlFor="admission-notes">Anything we should know?</label>
                      <textarea
                        id="admission-notes"
                        rows={3}
                        value={form.notes}
                        onChange={(event) => setForm({ ...form, notes: event.target.value })}
                        placeholder="Preferred batch timing, questions, or support needs"
                      />
                    </div>
                  </div>
                  <div className="admission-submit-row">
                    <p>
                      By submitting you agree to be contacted about this application. No payment
                      is collected on this form.
                    </p>
                    <button className="primary-button" disabled={submitting} type="submit">
                      {submitting ? 'Submitting…' : 'Submit application'}
                    </button>
                  </div>
                </form>
              )}
            </div>

            <aside className="admission-side">
              <div className="admission-side-card">
                <span className="eyebrow">YOUR SELECTION</span>
                <h3>{selectedCourse?.name ?? 'Choose a course'}</h3>
                <p>{selectedBranch?.name ?? 'Choose a branch'}</p>
                {selectedCourse && (
                  <dl className="admission-fees">
                    <div><dt>Duration</dt><dd>{selectedCourse.duration_months} months</dd></div>
                    <div><dt>Course fee</dt><dd>{inr(selectedCourse.fee_amount)}</dd></div>
                    <div><dt>Registration fee</dt><dd>{inr(selectedCourse.registration_fee)}</dd></div>
                  </dl>
                )}
                {selectedBranch?.address && <p className="admission-branch-note">{selectedBranch.address}</p>}
              </div>
              <div className="admission-side-card">
                <span className="eyebrow">WHAT YOU NEED</span>
                <ul className="admission-checklist">
                  <li>Aadhaar or another government ID</li>
                  <li>Latest marksheet or certificate</li>
                  <li>A recent passport-size photograph</li>
                  <li>Your contact and guardian details</li>
                </ul>
                <p className="admission-branch-note">
                  Documents can be uploaded after you submit. PDF, image, Word, Excel and ZIP
                  files up to 10 MB are accepted.
                </p>
              </div>
            </aside>
          </section>
        )}

        {tab === 'track' && (
          <section className="admission-layout">
            <div className="admission-card">
              <div className="admission-card-heading">
                <span className="eyebrow">APPLICATION TRACKER</span>
                <h2>Check your application</h2>
                <p>Use the application code and access token you received after applying.</p>
              </div>
              <form
                className="admission-track-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  void loadStatus()
                }}
              >
                <div className="field">
                  <label htmlFor="track-code">Application code</label>
                  <input
                    id="track-code"
                    value={trackCode}
                    onChange={(event) => setTrackCode(event.target.value.toUpperCase())}
                    placeholder="ADM-2026-XXXXXXXX"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="track-token">Access token</label>
                  <input
                    id="track-token"
                    value={trackToken}
                    onChange={(event) => setTrackToken(event.target.value)}
                    placeholder="Paste the token saved after applying"
                    required
                  />
                </div>
                <button className="primary-button" disabled={tracking} type="submit">
                  {tracking ? 'Checking…' : 'View application'}
                </button>
              </form>
              {trackError && <div className="inline-error">{trackError}</div>}

              {created && statusData?.application_code === created.application_code && (
                <div className="admission-success">
                  <strong>Application submitted successfully.</strong>
                  <p>Save these details. They are the only way to reopen your application.</p>
                  <div className="admission-secret-row">
                    <span><small>Application code</small><b>{created.application_code}</b></span>
                    <button className="secondary-button" onClick={() => void copy(created.application_code, 'Application code copied.')} type="button">Copy code</button>
                  </div>
                  <div className="admission-secret-row">
                    <span><small>Access token</small><b>{created.upload_token}</b></span>
                    <button className="secondary-button" onClick={() => void copy(created.upload_token, 'Access token copied.')} type="button">Copy token</button>
                  </div>
                </div>
              )}

              {statusData && (
                <div className="admission-status-panel">
                  <div className="admission-status-head">
                    <div>
                      <span className="eyebrow">{statusData.application_code}</span>
                      <h3>{statusData.full_name}</h3>
                      <p>{statusData.course_name} · {statusData.branch_name}</p>
                    </div>
                    <span className={`status-pill admission-status status-${statusData.status}`}>
                      <i />{label(statusData.status)}
                    </span>
                  </div>

                  {statusData.rejection_reason && (
                    <div className="admission-note">
                      <strong>Reviewer note</strong>
                      <p>{statusData.rejection_reason}</p>
                    </div>
                  )}

                  <div className="admission-meta-grid">
                    <div><small>Payment</small><b>{label(statusData.payment_status)}</b></div>
                    <div><small>Registration fee</small><b>{inr(statusData.registration_fee)}</b></div>
                    <div><small>Paid</small><b>{inr(statusData.total_paid)}</b></div>
                    <div><small>Applied on</small><b>{formatDate(statusData.created_at)}</b></div>
                    {statusData.student_code && <div><small>Student ID</small><b>{statusData.student_code}</b></div>}
                    {statusData.roll_number && <div><small>Roll number</small><b>{statusData.roll_number}</b></div>}
                    {statusData.enrollment_code && <div><small>Enrollment</small><b>{statusData.enrollment_code}</b></div>}
                  </div>

                  {canPay && (
                    <div className="admission-payment-block">
                      <div>
                        <strong>Registration fee {inr(statusData.registration_fee)}</strong>
                        <p>Pay at the branch or complete the secure online checkout.</p>
                      </div>
                      <button className="primary-button" disabled={paymentBusy} onClick={() => void startPayment()} type="button">
                        {paymentBusy ? 'Starting…' : 'Pay registration fee'}
                      </button>
                      {paymentIntent && <p className="admission-instructions">{paymentIntent.instructions}</p>}
                      {paymentError && <div className="inline-error">{paymentError}</div>}
                    </div>
                  )}

                  <div className="admission-doc-section">
                    <div className="section-title">
                      <div>
                        <span className="eyebrow">DOCUMENTS</span>
                        <h4>{statusData.documents.length} uploaded</h4>
                      </div>
                    </div>
                    {statusData.documents.length === 0 ? (
                      <p className="muted">No documents uploaded yet.</p>
                    ) : (
                      <ul className="admission-doc-list">
                        {statusData.documents.map((document) => (
                          <li key={document.id}>
                            <span>{document.title}<small>{document.file_name}</small></span>
                            <a href={`${api.defaults.baseURL ?? ''}${document.download_url}`} rel="noreferrer" target="_blank">Open</a>
                          </li>
                        ))}
                      </ul>
                    )}

                    {canUpload && (
                      <form className="admission-upload-form" onSubmit={uploadDocument}>
                        <div className="field">
                          <label htmlFor="admission-document-type">Document type</label>
                          <select
                            id="admission-document-type"
                            value={uploadType}
                            onChange={(event) => setUploadType(event.target.value)}
                          >
                            {DOCUMENT_TYPES.map((type) => (
                              <option key={type.value} value={type.value}>{type.label}</option>
                            ))}
                          </select>
                        </div>
                        <div className="field">
                          <label htmlFor="admission-document-title">Title (optional)</label>
                          <input
                            id="admission-document-title"
                            value={uploadTitle}
                            onChange={(event) => setUploadTitle(event.target.value)}
                            placeholder="e.g. Aadhaar front"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="admission-document-file">Choose file</label>
                          <input
                            id="admission-document-file"
                            type="file"
                            accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.zip"
                            onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                          />
                        </div>
                        <button className="secondary-button" disabled={uploading} type="submit">
                          {uploading ? 'Uploading…' : 'Upload document'}
                        </button>
                        {uploadMessage && <p className="admission-instructions">{uploadMessage}</p>}
                      </form>
                    )}
                  </div>

                  {statusData.payments.length > 0 && (
                    <div className="admission-doc-section">
                      <div className="section-title">
                        <div>
                          <span className="eyebrow">PAYMENTS</span>
                          <h4>Registration fee history</h4>
                        </div>
                      </div>
                      <ul className="admission-payment-list">
                        {statusData.payments.map((payment) => (
                          <li key={`${payment.created_at}-${payment.amount}-${payment.status}`}>
                            <span>
                              {inr(payment.amount)}
                              <small>
                                {label(payment.status)} · {payment.payment_method.replaceAll('_', ' ')}
                                {payment.invoice_number ? ` · ${payment.invoice_number}` : ''}
                              </small>
                            </span>
                            <b>{formatDate(payment.paid_at ?? payment.created_at)}</b>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>

            <aside className="admission-side">
              <div className="admission-side-card">
                <span className="eyebrow">NEED HELP?</span>
                <h3>Admissions desk</h3>
                <p>We are happy to help with your application, documents, or fee payment.</p>
                {catalog?.branches.map((branch) => (
                  <div className="admission-contact" key={branch.id}>
                    <strong>{branch.name}</strong>
                    {branch.address && <span>{branch.address}</span>}
                    {branch.phone && <a href={`tel:${branch.phone}`}>{branch.phone}</a>}
                    {branch.email && <a href={`mailto:${branch.email}`}>{branch.email}</a>}
                  </div>
                ))}
              </div>
              <div className="admission-side-card">
                <span className="eyebrow">PRIVACY</span>
                <h3>Your documents stay private</h3>
                <p>
                  Uploaded files are visible only to you with the access token and to authorised
                  institute staff. Keep the token confidential.
                </p>
              </div>
            </aside>
          </section>
        )}
      </main>

      <footer className="admission-footer">
        <span>© 2026 NICT Institute Management</span>
        <span>Admissions · <a href="/login">Staff sign in</a></span>
      </footer>
    </div>
  )
}

export default AdmissionPage
