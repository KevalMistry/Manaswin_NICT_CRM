import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser } from '../utils/auth'

type Admission = {
  id: number
  application_code: string
  full_name: string
  email: string | null
  phone: string
  date_of_birth: string | null
  gender: string | null
  parent_name: string | null
  parent_phone: string | null
  address: string | null
  qualification: string | null
  notes: string | null
  branch_id: number
  branch_name: string
  course_id: number
  course_name: string
  batch_id: number | null
  batch_name: string | null
  status: string
  payment_status: string
  registration_fee: string
  total_paid: string
  documents_count: number
  source: string
  review_notes: string | null
  rejection_reason: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  student_id: number | null
  student_code: string | null
  roll_number: string | null
  enrollment_id: number | null
  enrollment_code: string | null
  created_at: string
  updated_at: string
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
  id: number
  invoice_number: string | null
  amount: string
  taxable_amount: string
  gst_amount: string
  payment_method: string
  provider: string
  status: string
  reference: string | null
  provider_order_id: string | null
  provider_payment_id: string | null
  paid_at: string | null
  recorded_by: string | null
  created_at: string
}

type AdmissionDetail = Admission & {
  documents: AdmissionDocument[]
  payments: AdmissionPayment[]
}

type Stats = {
  total: number
  submitted: number
  under_review: number
  enrolled: number
  rejected: number
  withdrawn: number
  unpaid: number
  pending_payment: number
  paid: number
  fees_collected: string
}

type Batch = {
  id: number
  name: string
  code: string
  course_id: number
  branch_id: number
  capacity: number
  is_active: boolean
}

type BranchOption = { id: number; name: string; code: string; is_active: boolean }

type Invoice = {
  invoice_number: string
  invoice_date: string
  application_code: string
  applicant_name: string
  student_code: string | null
  roll_number: string | null
  course_name: string
  branch_name: string
  branch_address: string | null
  branch_phone: string | null
  branch_email: string | null
  branch_gstin: string | null
  amount: string
  taxable_amount: string
  gst_rate_percent: number
  gst_amount: string
  payment_method: string
  reference: string | null
  status: string
  paid_at: string | null
}

const STATUS_TABS = [
  { value: '', label: 'All applications' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under review' },
  { value: 'enrolled', label: 'Enrolled' },
  { value: 'rejected', label: 'Rejected' },
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

const PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'upi', label: 'UPI' },
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'card', label: 'Card' },
  { value: 'cheque', label: 'Cheque' },
]

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

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

const NUMBER_WORDS = [
  'Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
  'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
  'Seventeen', 'Eighteen', 'Nineteen',
]
const TENS_WORDS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

function twoDigits(value: number): string {
  if (value < 20) return NUMBER_WORDS[value]
  return `${TENS_WORDS[Math.floor(value / 10)]}${value % 10 ? `-${NUMBER_WORDS[value % 10]}` : ''}`
}

function threeDigits(value: number): string {
  if (value < 100) return twoDigits(value)
  const remainder = value % 100
  return `${NUMBER_WORDS[Math.floor(value / 100)]} Hundred${remainder ? ` ${twoDigits(remainder)}` : ''}`
}

/** Convert a rupee amount into Indian-numbering words for the printed receipt. */
function amountInWords(value: string | number): string {
  const numeric = Math.abs(Number(value))
  if (!Number.isFinite(numeric)) return ''
  const rupees = Math.floor(numeric)
  const paise = Math.round((numeric - rupees) * 100)
  if (rupees === 0 && paise === 0) return 'Zero Rupees Only'
  const parts: string[] = []
  const crore = Math.floor(rupees / 10000000)
  const lakh = Math.floor((rupees % 10000000) / 100000)
  const thousand = Math.floor((rupees % 100000) / 1000)
  const hundred = rupees % 1000
  if (crore) parts.push(`${threeDigits(crore)} Crore`)
  if (lakh) parts.push(`${twoDigits(lakh)} Lakh`)
  if (thousand) parts.push(`${twoDigits(thousand)} Thousand`)
  if (hundred) parts.push(threeDigits(hundred))
  const rupeeText = parts.length ? `${parts.join(' ')} Rupees` : ''
  if (!paise) return `${rupeeText} Only`
  return `${rupeeText}${rupeeText ? ' and' : ''} ${twoDigits(paise)} Paise Only`
}

function AdmissionsPage() {
  const user = getStoredUser()
  const isSuperAdmin = user?.role_name === 'Super Admin'
  const roleName = user?.role_name ?? ''
  // Keep the buttons in step with the API role guards so nobody hits a 403.
  const canManageReview = ['Super Admin', 'Branch Admin', 'Staff', 'Counsellor'].includes(roleName)
  const canRecordPayment = ['Super Admin', 'Branch Admin', 'Staff'].includes(roleName)
  const canReject = ['Super Admin', 'Branch Admin'].includes(roleName)
  const canOverrideFee = ['Super Admin', 'Branch Admin'].includes(roleName)

  const [rows, setRows] = useState<Admission[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [batches, setBatches] = useState<Batch[]>([])
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [statusTab, setStatusTab] = useState('')
  const [paymentFilter, setPaymentFilter] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [detail, setDetail] = useState<AdmissionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionBusy, setActionBusy] = useState('')
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [approveForm, setApproveForm] = useState({
    batch_id: '',
    discount_amount: '0',
    notes: '',
    override_unpaid_fee: false,
  })
  const [paymentForm, setPaymentForm] = useState({
    amount: '',
    payment_method: 'cash',
    payment_date: today(),
    reference: '',
  })
  const [invoice, setInvoice] = useState<Invoice | null>(null)

  useEffect(() => {
    document.body.classList.toggle('invoice-print', Boolean(invoice))
    return () => document.body.classList.remove('invoice-print')
  }, [invoice])

  const loadReferenceData = useCallback(async () => {
    const [batchRes, branchRes] = await Promise.all([
      api.get<Batch[]>('/api/batches', { params: { include_inactive: true } }).catch(() => ({ data: [] as Batch[] })),
      api.get<BranchOption[]>('/api/branches', { params: { include_inactive: true } }).catch(() => ({ data: [] as BranchOption[] })),
    ])
    setBatches(batchRes.data)
    setBranches(branchRes.data)
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string | number> = {}
      if (statusTab) params.status = statusTab
      if (paymentFilter) params.payment_status = paymentFilter
      if (branchFilter) params.branch_id = Number(branchFilter)
      if (search.trim()) params.search = search.trim()
      const [listRes, statsRes] = await Promise.all([
        api.get<Admission[]>('/api/admissions', { params }),
        api.get<Stats>('/api/admissions/stats'),
      ])
      setRows(listRes.data)
      setStats(statsRes.data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load admission applications.'))
    } finally {
      setLoading(false)
    }
  }, [branchFilter, paymentFilter, search, statusTab])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadReferenceData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadReferenceData])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadList(), 250)
    return () => window.clearTimeout(timer)
  }, [loadList])

  const matchingBatches = useMemo(() => {
    if (!detail) return []
    return batches.filter(
      (batch) => batch.course_id === detail.course_id && batch.branch_id === detail.branch_id && batch.is_active,
    )
  }, [batches, detail])

  function prepareDetail(data: AdmissionDetail) {
    setDetail(data)
    setRejectOpen(false)
    setRejectReason('')
    const firstBatch = batches.find(
      (batch) => batch.course_id === data.course_id && batch.branch_id === data.branch_id && batch.is_active,
    )
    setApproveForm({
      batch_id: data.batch_id ? String(data.batch_id) : firstBatch ? String(firstBatch.id) : '',
      discount_amount: '0',
      notes: '',
      override_unpaid_fee: data.status === 'approved',
    })
    setPaymentForm({
      amount: data.registration_fee,
      payment_method: 'cash',
      payment_date: today(),
      reference: '',
    })
  }

  async function openDetail(id: number) {
    setDetailLoading(true)
    setError('')
    setMessage('')
    try {
      const { data } = await api.get<AdmissionDetail>(`/api/admissions/${id}`)
      prepareDetail(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load this application.'))
    } finally {
      setDetailLoading(false)
    }
  }

  async function refreshDetail(id: number) {
    const { data } = await api.get<AdmissionDetail>(`/api/admissions/${id}`)
    prepareDetail(data)
  }

  async function markUnderReview() {
    if (!detail) return
    setActionBusy('review')
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<AdmissionDetail>(`/api/admissions/${detail.id}/status`, {
        status: 'under_review',
      })
      prepareDetail(data)
      setMessage('Application moved to under review.')
      await loadList()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to update the application.'))
    } finally {
      setActionBusy('')
    }
  }

  async function rejectApplication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!detail) return
    setActionBusy('reject')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<AdmissionDetail>(`/api/admissions/${detail.id}/reject`, {
        reason: rejectReason.trim(),
      })
      prepareDetail(data)
      setMessage('Application rejected.')
      await loadList()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to reject the application.'))
    } finally {
      setActionBusy('')
    }
  }

  async function recordPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!detail) return
    setActionBusy('payment')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<AdmissionPayment>(`/api/admissions/${detail.id}/payments`, {
        amount: paymentForm.amount ? Number(paymentForm.amount) : null,
        payment_method: paymentForm.payment_method,
        payment_date: paymentForm.payment_date || null,
        reference: paymentForm.reference || null,
      })
      setMessage(`Payment recorded · invoice ${data.invoice_number ?? 'generated'}.`)
      await Promise.all([loadList(), refreshDetail(detail.id)])
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to record the payment.'))
    } finally {
      setActionBusy('')
    }
  }

  async function approveApplication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!detail) return
    if (!approveForm.batch_id) {
      setError('Choose a batch before approving this application.')
      return
    }
    setActionBusy('approve')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<{
        application: AdmissionDetail
        student_code: string
        roll_number: string
        enrollment_code: string
      }>(`/api/admissions/${detail.id}/approve`, {
        batch_id: Number(approveForm.batch_id),
        discount_amount: Number(approveForm.discount_amount || 0),
        notes: approveForm.notes || null,
        override_unpaid_fee: approveForm.override_unpaid_fee,
      })
      prepareDetail(data.application)
      setMessage(
        `Enrolled as ${data.student_code} (roll ${data.roll_number}) with enrollment ${data.enrollment_code}.`,
      )
      await loadList()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to approve this application.'))
    } finally {
      setActionBusy('')
    }
  }

  async function showInvoice(paymentId?: number) {
    if (!detail) return
    setError('')
    try {
      const { data } = await api.get<Invoice>(`/api/admissions/${detail.id}/invoice`, {
        params: paymentId ? { payment_id: paymentId } : {},
      })
      setInvoice(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the invoice.'))
    }
  }

  async function openDocument(document: AdmissionDocument) {
    setError('')
    try {
      const response = await api.get(document.download_url, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data as Blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to open this document.'))
    }
  }

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">ADMISSIONS</span>
          <h1>Online admissions</h1>
          <p>Review applications, collect registration fees, and enrol students.</p>
        </div>
        <div className="heading-actions">
          <button className="secondary-button" onClick={() => void loadList()} type="button">Refresh</button>
          <a className="primary-button admission-public-link" href="/admission" rel="noreferrer" target="_blank">
            Open public form
          </a>
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="metric-grid admission-metrics">
        <div className="metric-card">
          <div className="metric-icon blue">▤</div>
          <span className="metric-label">Total applications</span>
          <div className="metric-value">{stats?.total ?? 0}</div>
          <span className="metric-detail">Across your branches</span>
        </div>
        <div className="metric-card">
          <div className="metric-icon orange">◷</div>
          <span className="metric-label">Awaiting review</span>
          <div className="metric-value">{(stats?.submitted ?? 0) + (stats?.under_review ?? 0)}</div>
          <span className="metric-detail">Submitted or under review</span>
        </div>
        <div className="metric-card">
          <div className="metric-icon green">✓</div>
          <span className="metric-label">Enrolled</span>
          <div className="metric-value">{stats?.enrolled ?? 0}</div>
          <span className="metric-detail">Students created</span>
        </div>
        <div className="metric-card">
          <div className="metric-icon violet">₹</div>
          <span className="metric-label">Registration fees</span>
          <div className="metric-value">{inr(stats?.fees_collected)}</div>
          <span className="metric-detail">{stats?.paid ?? 0} paid applications</span>
        </div>
      </section>

      <section className="module-tabs admission-tabs">
        {STATUS_TABS.map((tab) => (
          <button
            className={statusTab === tab.value ? 'active-tab' : ''}
            key={tab.value || 'all'}
            onClick={() => setStatusTab(tab.value)}
            type="button"
          >
            {tab.label}
            {tab.value === '' && <span>{stats?.total ?? 0}</span>}
            {tab.value === 'submitted' && <span>{stats?.submitted ?? 0}</span>}
            {tab.value === 'under_review' && <span>{stats?.under_review ?? 0}</span>}
            {tab.value === 'enrolled' && <span>{stats?.enrolled ?? 0}</span>}
            {tab.value === 'rejected' && <span>{stats?.rejected ?? 0}</span>}
          </button>
        ))}
      </section>

      <section className="module-toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input
            aria-label="Search applications"
            placeholder="Search name, code, email or phone…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="toolbar-controls">
          <select aria-label="Filter by payment" value={paymentFilter} onChange={(event) => setPaymentFilter(event.target.value)}>
            <option value="">All payments</option>
            <option value="unpaid">Unpaid</option>
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
          </select>
          {isSuperAdmin && (
            <select aria-label="Filter by branch" value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}>
              <option value="">All branches</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
          )}
          <span className="result-count">{rows.length} results</span>
        </div>
      </section>

      <section className="data-panel">
        {loading ? (
          <div className="table-state">Loading applications…</div>
        ) : rows.length === 0 ? (
          <div className="table-state">
            <div className="empty-icon">▤</div>
            <strong>No applications found</strong>
            <p>Share the public admission form to start receiving applications.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="admission-table">
              <thead>
                <tr>
                  <th>Applicant</th>
                  <th>Program</th>
                  <th>Applied</th>
                  <th>Registration fee</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <div className="admission-applicant">
                        <span className="branch-avatar">{row.full_name.slice(0, 1).toUpperCase()}</span>
                        <span>
                          <strong>{row.full_name}</strong>
                          <small>{row.application_code}</small>
                          <small>{row.phone}{row.email ? ` · ${row.email}` : ''}</small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <strong className="admission-cell-strong">{row.course_name}</strong>
                      <small className="admission-cell-sub">{row.branch_name}</small>
                    </td>
                    <td>{formatDate(row.created_at)}</td>
                    <td>
                      <strong className="admission-cell-strong">{inr(row.registration_fee)}</strong>
                      <span className={`status-pill payment-${row.payment_status}`}>
                        <i />{label(row.payment_status)}
                      </span>
                    </td>
                    <td>
                      <span className={`status-pill admission-status status-${row.status}`}>
                        <i />{label(row.status)}
                      </span>
                      {row.roll_number && <small className="admission-cell-sub">{row.roll_number}</small>}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button onClick={() => void openDetail(row.id)} type="button">
                          {row.status === 'enrolled' ? 'View' : 'Review'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {(detail || detailLoading) && (
        <div
          className="modal-backdrop admission-admin-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setDetail(null)
          }}
          role="presentation"
        >
          <div aria-modal="true" className="modal-card admission-detail-modal" role="dialog">
            {detailLoading && !detail ? (
              <div className="table-state">Loading application…</div>
            ) : detail ? (
              <>
                <div className="modal-header">
                  <div>
                    <span className="eyebrow">{detail.application_code}</span>
                    <h2>{detail.full_name}</h2>
                    <p>{detail.course_name} · {detail.branch_name}</p>
                  </div>
                  <button className="close-button" onClick={() => setDetail(null)} type="button">×</button>
                </div>

                <div className="admission-detail-badges">
                  <span className={`status-pill admission-status status-${detail.status}`}>
                    <i />{label(detail.status)}
                  </span>
                  <span className={`status-pill payment-${detail.payment_status}`}>
                    <i />Payment {label(detail.payment_status)}
                  </span>
                  <span className="code-pill">{inr(detail.registration_fee)} registration fee</span>
                </div>

                <div className="admission-detail-grid">
                  <div><small>Mobile</small><b>{detail.phone}</b></div>
                  <div><small>Email</small><b>{detail.email ?? '—'}</b></div>
                  <div><small>Date of birth</small><b>{formatDate(detail.date_of_birth)}</b></div>
                  <div><small>Gender</small><b>{detail.gender ?? '—'}</b></div>
                  <div><small>Parent / guardian</small><b>{detail.parent_name ?? '—'}</b></div>
                  <div><small>Parent mobile</small><b>{detail.parent_phone ?? '—'}</b></div>
                  <div><small>Qualification</small><b>{detail.qualification ?? '—'}</b></div>
                  <div><small>Source</small><b>{detail.source.replaceAll('_', ' ')}</b></div>
                  <div className="full-field"><small>Address</small><b>{detail.address ?? '—'}</b></div>
                  {detail.notes && <div className="full-field"><small>Applicant notes</small><b>{detail.notes}</b></div>}
                  {detail.review_notes && <div className="full-field"><small>Review notes</small><b>{detail.review_notes}</b></div>}
                  {detail.rejection_reason && <div className="full-field"><small>Rejection reason</small><b>{detail.rejection_reason}</b></div>}
                </div>

                <div className="admission-detail-section">
                  <div className="section-title">
                    <div>
                      <span className="eyebrow">DOCUMENTS</span>
                      <h4>{detail.documents.length} uploaded</h4>
                    </div>
                  </div>
                  {detail.documents.length === 0 ? (
                    <p className="muted">No documents uploaded.</p>
                  ) : (
                    <ul className="admission-doc-list">
                      {detail.documents.map((document) => (
                        <li key={document.id}>
                          <span>{document.title}<small>{document.file_name}</small></span>
                          <button className="text-button" onClick={() => void openDocument(document)} type="button">Open</button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="admission-detail-section">
                  <div className="section-title">
                    <div>
                      <span className="eyebrow">PAYMENTS</span>
                      <h4>{inr(detail.total_paid)} collected</h4>
                    </div>
                    {detail.payments.some((payment) => payment.status === 'paid') && (
                      <button className="secondary-button" onClick={() => void showInvoice()} type="button">Print invoice</button>
                    )}
                  </div>
                  {detail.payments.length === 0 ? (
                    <p className="muted">No payments recorded.</p>
                  ) : (
                    <ul className="admission-payment-list">
                      {detail.payments.map((payment) => (
                        <li key={payment.id}>
                          <span>
                            {inr(payment.amount)}
                            <small>
                              {label(payment.status)} · {payment.payment_method.replaceAll('_', ' ')}
                              {payment.invoice_number ? ` · ${payment.invoice_number}` : ''}
                              {payment.recorded_by ? ` · by ${payment.recorded_by}` : ''}
                            </small>
                          </span>
                          <span className="admission-payment-actions">
                            <b>{formatDate(payment.paid_at ?? payment.created_at)}</b>
                            {payment.status === 'paid' && payment.invoice_number && (
                              <button className="text-button" onClick={() => void showInvoice(payment.id)} type="button">Invoice</button>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {canRecordPayment && detail.status !== 'rejected' && detail.status !== 'withdrawn' && (
                    <form className="admission-inline-form" onSubmit={recordPayment}>
                      <div className="field">
                        <label htmlFor="payment-amount">Amount (₹)</label>
                        <input
                          id="payment-amount"
                          type="number"
                          min="0"
                          step="0.01"
                          value={paymentForm.amount}
                          onChange={(event) => setPaymentForm({ ...paymentForm, amount: event.target.value })}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="payment-method">Method</label>
                        <select
                          id="payment-method"
                          value={paymentForm.payment_method}
                          onChange={(event) => setPaymentForm({ ...paymentForm, payment_method: event.target.value })}
                        >
                          {PAYMENT_METHODS.map((method) => (
                            <option key={method.value} value={method.value}>{method.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="field">
                        <label htmlFor="payment-date">Payment date</label>
                        <input
                          id="payment-date"
                          type="date"
                          value={paymentForm.payment_date}
                          onChange={(event) => setPaymentForm({ ...paymentForm, payment_date: event.target.value })}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="payment-reference">Reference</label>
                        <input
                          id="payment-reference"
                          value={paymentForm.reference}
                          onChange={(event) => setPaymentForm({ ...paymentForm, reference: event.target.value })}
                          placeholder="UPI / cheque reference"
                        />
                      </div>
                      <button className="secondary-button" disabled={actionBusy === 'payment'} type="submit">
                        {actionBusy === 'payment' ? 'Recording…' : 'Record payment'}
                      </button>
                    </form>
                  )}
                </div>

                {canManageReview && detail.status !== 'rejected' && detail.status !== 'withdrawn' && detail.status !== 'enrolled' && (
                  <div className="admission-detail-section admission-review-actions">
                    <div className="section-title">
                      <div>
                        <span className="eyebrow">REVIEW</span>
                        <h4>Admission decision</h4>
                      </div>
                      {detail.status === 'submitted' && (
                        <button
                          className="secondary-button"
                          disabled={actionBusy === 'review'}
                          onClick={() => void markUnderReview()}
                          type="button"
                        >
                          Mark under review
                        </button>
                      )}
                    </div>

                    <form className="admission-approve-form" onSubmit={approveApplication}>
                      <div className="field">
                        <label htmlFor="approve-batch">Assign batch</label>
                        <select
                          id="approve-batch"
                          value={approveForm.batch_id}
                          onChange={(event) => setApproveForm({ ...approveForm, batch_id: event.target.value })}
                          required
                        >
                          <option value="">Select batch</option>
                          {matchingBatches.map((batch) => (
                            <option key={batch.id} value={batch.id}>{batch.name} · {batch.code}</option>
                          ))}
                        </select>
                        {matchingBatches.length === 0 && (
                          <small className="field-hint">
                            Create an active batch for this course and branch before approving.
                          </small>
                        )}
                      </div>
                      <div className="field">
                        <label htmlFor="approve-discount">Discount (₹)</label>
                        <input
                          id="approve-discount"
                          type="number"
                          min="0"
                          step="0.01"
                          value={approveForm.discount_amount}
                          onChange={(event) => setApproveForm({ ...approveForm, discount_amount: event.target.value })}
                        />
                        <small className="field-hint">Applied to the course fee plan.</small>
                      </div>
                      <div className="field full-field">
                        <label htmlFor="approve-notes">Review notes</label>
                        <textarea
                          id="approve-notes"
                          rows={2}
                          value={approveForm.notes}
                          onChange={(event) => setApproveForm({ ...approveForm, notes: event.target.value })}
                        />
                      </div>
                      {detail.payment_status !== 'paid' && canOverrideFee && (
                        <label className="admission-checkbox full-field">
                          <input
                            checked={approveForm.override_unpaid_fee}
                            onChange={(event) => setApproveForm({ ...approveForm, override_unpaid_fee: event.target.checked })}
                            type="checkbox"
                          />
                          <span>Override unpaid registration fee (administrators only)</span>
                        </label>
                      )}
                      <div className="admission-approve-actions full-field">
                        <button
                          className="primary-button"
                          disabled={actionBusy === 'approve' || matchingBatches.length === 0}
                          type="submit"
                        >
                          {actionBusy === 'approve' ? 'Enrolling…' : 'Approve & enrol student'}
                        </button>
                        {canReject && (
                          <button className="danger-action" onClick={() => setRejectOpen((open) => !open)} type="button">
                            Reject application
                          </button>
                        )}
                      </div>
                    </form>

                    {canReject && rejectOpen && (
                      <form className="admission-reject-form" onSubmit={rejectApplication}>
                        <div className="field">
                          <label htmlFor="reject-reason">Reason for rejection</label>
                          <textarea
                            id="reject-reason"
                            rows={2}
                            value={rejectReason}
                            onChange={(event) => setRejectReason(event.target.value)}
                            required
                          />
                        </div>
                        <button className="danger-action" disabled={actionBusy === 'reject'} type="submit">
                          {actionBusy === 'reject' ? 'Rejecting…' : 'Confirm rejection'}
                        </button>
                      </form>
                    )}
                  </div>
                )}

                {detail.status === 'enrolled' && (
                  <div className="admission-enrolled-card">
                    <strong>Student enrolled</strong>
                    <div>
                      <span><small>Student ID</small><b>{detail.student_code}</b></span>
                      <span><small>Roll number</small><b>{detail.roll_number ?? '—'}</b></span>
                      <span><small>Enrollment</small><b>{detail.enrollment_code}</b></span>
                      <span><small>Batch</small><b>{detail.batch_name ?? '—'}</b></span>
                    </div>
                    <p>Documents were copied to the student record and a fee plan was created when applicable.</p>
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}

      {invoice && (
        <div className="modal-backdrop invoice-backdrop" role="presentation">
          <div aria-modal="true" className="modal-card invoice-card" role="dialog">
            <div className="modal-header invoice-header">
              <div>
                <span className="eyebrow">GST INVOICE / RECEIPT</span>
                <h2>{invoice.invoice_number}</h2>
              </div>
              <div className="invoice-toolbar">
                <button className="secondary-button" onClick={() => window.print()} type="button">Print</button>
                <button className="close-button" onClick={() => setInvoice(null)} type="button">×</button>
              </div>
            </div>
            <div className="invoice-sheet">
              <div className="invoice-head">
                <div>
                  <h3>{invoice.branch_name}</h3>
                  {invoice.branch_address && <p>{invoice.branch_address}</p>}
                  {invoice.branch_phone && <p>Phone: {invoice.branch_phone}</p>}
                  {invoice.branch_email && <p>{invoice.branch_email}</p>}
                  <p>GSTIN: {invoice.branch_gstin ?? 'Not configured'}</p>
                </div>
                <div className="invoice-head-right">
                  <strong>TAX INVOICE</strong>
                  <span>{invoice.invoice_number}</span>
                  <span>Date: {formatDate(invoice.invoice_date)}</span>
                </div>
              </div>
              <div className="invoice-parties">
                <div>
                  <small>Billed to</small>
                  <strong>{invoice.applicant_name}</strong>
                  <span>Application {invoice.application_code}</span>
                  {invoice.student_code && <span>Student ID: {invoice.student_code}</span>}
                  {invoice.roll_number && <span>Roll number: {invoice.roll_number}</span>}
                </div>
                <div>
                  <small>Payment</small>
                  <strong>{label(invoice.status)}</strong>
                  <span>{invoice.payment_method.replaceAll('_', ' ')}</span>
                  {invoice.reference && <span>Ref: {invoice.reference}</span>}
                  <span>{formatDate(invoice.paid_at)}</span>
                </div>
              </div>
              <table className="invoice-table">
                <thead>
                  <tr><th>Description</th><th>Taxable value</th><th>GST ({invoice.gst_rate_percent}%)</th><th>Total</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Admission registration fee · {invoice.course_name}</td>
                    <td>{inr(invoice.taxable_amount)}</td>
                    <td>{inr(invoice.gst_amount)}</td>
                    <td>{inr(invoice.amount)}</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr><td colSpan={3}>Total paid (GST inclusive)</td><td>{inr(invoice.amount)}</td></tr>
                </tfoot>
              </table>
              <p className="invoice-note">
                This is a computer-generated receipt for the admission registration fee. GST is
                included in the amount shown. Amount in words: {amountInWords(invoice.amount)}.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default AdmissionsPage
