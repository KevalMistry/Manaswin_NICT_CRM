import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { todayInputValue } from '../utils/date'
import { buildFeePlanRows } from '../utils/fees'

type Installment = {
  id: number
  installment_number: number
  amount: number
  paid_amount: number
  remaining_amount: number
  due_date: string
  status: string
}

type FeePlan = {
  id: number
  enrollment_id: number
  total_amount: number
  discount_amount: number
  scholarship_amount: number
  created_at: string
}

type Overview = {
  enrollment_id: number
  student_id: number
  student_name: string
  enrollment_code: string
  batch_id: number
  admission_date: string
  course_name: string
  course_fee: number | string | null
  fee_plan: FeePlan | null
  installments: Installment[]
  total_paid: number | string
  balance: number | string
}

type Receipt = {
  receipt_number: string
  student_name: string
  student_code: string
  student_email: string | null
  student_phone: string | null
  course_name: string
  batch_name: string
  installment_number: number
  amount: number
  payment_method: string
  payment_date: string
  reference: string | null
  total_fee: number
  total_paid: number
  balance: number
  branch_name: string
  branch_address: string | null
  branch_phone: string | null
}

type FeeReminderRow = {
  installment_id: number
  enrollment_id: number
  student_id: number
  student_name: string
  student_code: string
  email: string | null
  phone: string | null
  course_name: string
  batch_name: string
  branch_name: string
  installment_number: number
  remaining_amount: number | string
  due_date: string
  days_overdue: number
  status: string
}

type ReminderSendResult = {
  sent_count: number
  skipped_count: number
  failed_count: number
  recipients: string[]
  skipped: string[]
  failed: string[]
}

type PaymentMode = 'one_time' | 'installments'

type PlanDraft = {
  total: string
  discount: string
  scholarship: string
  firstDueDate: string
  mode: PaymentMode
  count: number
}

const INSTALLMENT_OPTIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function formatMoney(value: number | string | null | undefined): string {
  return `₹${Number(value ?? 0).toLocaleString('en-IN', {
    maximumFractionDigits: 2,
  })}`
}

function displayDate(value: string): string {
  if (!value) return '—'
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function FeesPage() {
  const [items, setItems] = useState<Overview[]>([])
  const [search, setSearch] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selected, setSelected] = useState<Overview | null>(null)
  const [planForm, setPlanForm] = useState<PlanDraft>({
    total: '',
    discount: '0',
    scholarship: '0',
    firstDueDate: todayInputValue(),
    mode: 'one_time',
    count: 3,
  })
  const [paymentForm, setPaymentForm] = useState({
    installmentId: '',
    amount: '',
    method: 'cash',
    date: todayInputValue(),
    reference: '',
  })
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [receiptPaymentId, setReceiptPaymentId] = useState<number | null>(null)
  const [emailingReceipt, setEmailingReceipt] = useState(false)
  const [receiptEmailMessage, setReceiptEmailMessage] = useState('')
  const [whatsappingReceipt, setWhatsappingReceipt] = useState(false)
  const [receiptWhatsAppMessage, setReceiptWhatsAppMessage] = useState('')
  const [saving, setSaving] = useState(false)

  const [remindersOpen, setRemindersOpen] = useState(false)
  const [reminders, setReminders] = useState<FeeReminderRow[]>([])
  const [reminderDaysAhead, setReminderDaysAhead] = useState('7')
  const [remindersLoading, setRemindersLoading] = useState(false)
  const [reminderSelection, setReminderSelection] = useState<number[]>([])
  const [sendingReminders, setSendingReminders] = useState(false)
  const [reminderResult, setReminderResult] = useState<ReminderSendResult | null>(null)
  const [sendingWhatsAppReminders, setSendingWhatsAppReminders] = useState(false)
  const [whatsAppReminderResult, setWhatsAppReminderResult] = useState<ReminderSendResult | null>(null)

  async function load() {
    setIsLoading(true)
    try {
      const { data } = await api.get<Overview[]>('/api/fees/overview')
      setItems(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load fee records.'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  const netAmount = roundMoney(
    Number(planForm.total || 0) -
      Number(planForm.discount || 0) -
      Number(planForm.scholarship || 0),
  )
  const installmentCount = planForm.mode === 'one_time' ? 1 : planForm.count
  const planRows = useMemo(
    () => buildFeePlanRows(netAmount, installmentCount, planForm.firstDueDate),
    [netAmount, installmentCount, planForm.firstDueDate],
  )

  function openPlan(item: Overview) {
    const courseFee = Number(item.course_fee ?? 0)
    setSelected(item)
    setPlanForm({
      total: courseFee > 0 ? String(courseFee) : '',
      discount: '0',
      scholarship: '0',
      firstDueDate: todayInputValue(),
      mode: 'one_time',
      count: 3,
    })
    setError('')
    setMessage('')
  }

  function openPayment(item: Overview) {
    const installment = item.installments.find((value) => Number(value.remaining_amount) > 0)
    setSelected(item)
    setPaymentForm({
      installmentId: String(installment?.id ?? ''),
      amount: String(installment ? Number(installment.remaining_amount) : ''),
      method: 'cash',
      date: todayInputValue(),
      reference: '',
    })
    setError('')
    setMessage('')
  }

  function updatePlan(changes: Partial<PlanDraft>) {
    setPlanForm((current) => ({ ...current, ...changes }))
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    if (planRows.length === 0) {
      setError('Enter a total fee greater than zero after discounts and scholarship.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await api.post('/api/fees/plans', {
        enrollment_id: selected.enrollment_id,
        total_amount: planForm.total,
        discount_amount: planForm.discount || '0',
        scholarship_amount: planForm.scholarship || '0',
        installments: planRows.map((row, index) => ({
          installment_number: index + 1,
          amount: row.amount,
          due_date: row.dueDate,
        })),
      })
      setSelected(null)
      setMessage(
        `Fee plan created for ${selected.student_name} with ${planRows.length} ${
          planRows.length === 1 ? 'payment' : 'installments'
        }.`,
      )
      await load()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to create the fee plan.'))
    } finally {
      setSaving(false)
    }
  }

  async function recordPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<{ id: number }>(
        `/api/fees/installments/${paymentForm.installmentId}/payments`,
        {
          amount: paymentForm.amount,
          payment_method: paymentForm.method,
          payment_date: paymentForm.date,
          receipt_number: paymentForm.reference || null,
        },
      )
      setSelected(null)
      setMessage('Payment recorded and receipt generated.')
      setReceiptPaymentId(data.id)
      setReceiptEmailMessage('')
      await load()
      try {
        const receiptResponse = await api.get<Receipt>(`/api/fees/payments/${data.id}/receipt`)
        setReceipt(receiptResponse.data)
      } catch {
        setError('Payment recorded, but the receipt could not be loaded.')
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to record this payment.'))
    } finally {
      setSaving(false)
    }
  }

  function closeReceipt() {
    setReceipt(null)
    setReceiptPaymentId(null)
    setReceiptEmailMessage('')
    setReceiptWhatsAppMessage('')
    setEmailingReceipt(false)
    setWhatsappingReceipt(false)
  }

  async function whatsappReceipt() {
    if (!receiptPaymentId) {
      setReceiptWhatsAppMessage('Reopen the receipt before sending it on WhatsApp.')
      return
    }
    setWhatsappingReceipt(true)
    setReceiptWhatsAppMessage('')
    setError('')
    try {
      const { data } = await api.post<{ sent: boolean; recipient: string | null; message: string }>(
        `/api/fees/payments/${receiptPaymentId}/whatsapp-receipt`,
      )
      setReceiptWhatsAppMessage(data.message)
    } catch (requestError) {
      setReceiptWhatsAppMessage(
        apiErrorMessage(requestError, 'Unable to send this receipt on WhatsApp. Check the phone number and WhatsApp settings.'),
      )
    } finally {
      setWhatsappingReceipt(false)
    }
  }

  async function emailReceipt() {
    if (!receiptPaymentId) {
      setReceiptEmailMessage('Reopen the receipt before emailing it.')
      return
    }
    setEmailingReceipt(true)
    setReceiptEmailMessage('')
    setError('')
    try {
      const { data } = await api.post<{ sent: boolean; recipient: string | null; message: string }>(
        `/api/fees/payments/${receiptPaymentId}/email-receipt`,
      )
      setReceiptEmailMessage(data.message)
    } catch (requestError) {
      setReceiptEmailMessage(
        apiErrorMessage(requestError, 'Unable to email this receipt. Check the student email and mail settings.'),
      )
    } finally {
      setEmailingReceipt(false)
    }
  }

  async function loadReminders(daysAhead = reminderDaysAhead) {
    setRemindersLoading(true)
    setError('')
    setReminderResult(null)
    setWhatsAppReminderResult(null)
    try {
      const { data } = await api.get<FeeReminderRow[]>('/api/fees/reminders', {
        params: { days_ahead: Number(daysAhead) || 0 },
      })
      setReminders(data)
      setReminderSelection(
        data.filter((row) => row.email || row.phone).map((row) => row.installment_id),
      )
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load pending fee installments.'))
    } finally {
      setRemindersLoading(false)
    }
  }

  function openReminders() {
    setRemindersOpen(true)
    setReminderResult(null)
    setWhatsAppReminderResult(null)
    void loadReminders(reminderDaysAhead)
  }

  function closeReminders() {
    setRemindersOpen(false)
    setReminders([])
    setReminderSelection([])
    setReminderResult(null)
    setWhatsAppReminderResult(null)
  }

  function toggleReminder(installmentId: number) {
    setReminderSelection((current) =>
      current.includes(installmentId)
        ? current.filter((value) => value !== installmentId)
        : [...current, installmentId],
    )
  }

  function toggleAllReminders() {
    const selectableIds = reminders
      .filter((row) => row.email || row.phone)
      .map((row) => row.installment_id)
    setReminderSelection((current) =>
      current.length === selectableIds.length ? [] : selectableIds,
    )
  }

  async function sendReminders() {
    if (reminderSelection.length === 0) {
      setError('Select at least one pending installment.')
      return
    }
    setSendingReminders(true)
    setError('')
    setReminderResult(null)
    try {
      const { data } = await api.post<ReminderSendResult>('/api/fees/reminders/send', {
        installment_ids: reminderSelection,
        days_ahead: Number(reminderDaysAhead) || 0,
      })
      setReminderResult(data)
      setMessage(
        `Fee reminders sent to ${data.sent_count} ${
          data.sent_count === 1 ? 'student' : 'students'
        }.`,
      )
      await loadReminders(reminderDaysAhead)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to send fee reminders.'))
    } finally {
      setSendingReminders(false)
    }
  }

  async function sendWhatsAppReminders() {
    if (reminderSelection.length === 0) {
      setError('Select at least one pending installment.')
      return
    }
    setSendingWhatsAppReminders(true)
    setError('')
    setWhatsAppReminderResult(null)
    try {
      const { data } = await api.post<ReminderSendResult>(
        '/api/fees/reminders/send-whatsapp',
        {
          installment_ids: reminderSelection,
          days_ahead: Number(reminderDaysAhead) || 0,
        },
      )
      setWhatsAppReminderResult(data)
      setMessage(
        `WhatsApp fee reminders sent to ${data.sent_count} ${
          data.sent_count === 1 ? 'student' : 'students'
        }.`,
      )
      await loadReminders(reminderDaysAhead)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to send WhatsApp fee reminders.'))
    } finally {
      setSendingWhatsAppReminders(false)
    }
  }

  const filtered = items.filter((item) =>
    `${item.student_name} ${item.enrollment_code} ${item.course_name}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )
  const totalCollected = items.reduce((sum, item) => sum + Number(item.total_paid), 0)
  const totalPending = items.reduce((sum, item) => sum + Number(item.balance), 0)
  const nextInstallment = selected
    ? selected.installments.find((value) => Number(value.remaining_amount) > 0)
    : undefined

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">FINANCE</span>
          <h1>Fee management</h1>
          <p>Create fee plans from course fees, record payments, and print receipts.</p>
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="metric-grid fee-metrics">
        <article className="metric-card">
          <div className="metric-label">Fee records</div>
          <div className="metric-value">{items.length}</div>
          <div className="metric-detail">Active enrollments</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Collected</div>
          <div className="metric-value">{formatMoney(totalCollected)}</div>
          <div className="metric-detail">Payments recorded</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Pending</div>
          <div className="metric-value">{formatMoney(totalPending)}</div>
          <div className="metric-detail">Outstanding balance</div>
        </article>
      </section>

      <section className="module-toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input
            aria-label="Search fee records"
            placeholder="Search student, course or enrollment…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <span className="result-count">{filtered.length} records</span>
        <div className="toolbar-controls">
          <button className="secondary-button" onClick={openReminders} type="button">
            Fee reminders
          </button>
        </div>
      </section>

      <section className="data-panel">
        {isLoading ? (
          <div className="table-state">Loading fee records…</div>
        ) : filtered.length === 0 ? (
          <div className="table-state">
            <div className="empty-icon">₹</div>
            <strong>No fee records found</strong>
            <p>Fee records appear automatically when students are enrolled.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Course</th>
                  <th>Course fee</th>
                  <th>Plan total</th>
                  <th>Paid</th>
                  <th>Balance</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const planTotal = item.fee_plan
                    ? Number(item.fee_plan.total_amount) -
                      Number(item.fee_plan.discount_amount) -
                      Number(item.fee_plan.scholarship_amount)
                    : null
                  const balance = Number(item.balance)
                  return (
                    <tr key={item.enrollment_id}>
                      <td>
                        <div className="branch-name">
                          <span className="branch-avatar">
                            {item.student_name.slice(0, 1).toUpperCase()}
                          </span>
                          <span>
                            <strong>{item.student_name}</strong>
                            <small>{item.enrollment_code}</small>
                          </span>
                        </div>
                      </td>
                      <td>{item.course_name}</td>
                      <td>
                        {Number(item.course_fee ?? 0) > 0
                          ? formatMoney(item.course_fee)
                          : 'Not set'}
                      </td>
                      <td>{planTotal === null ? '—' : formatMoney(planTotal)}</td>
                      <td>{formatMoney(item.total_paid)}</td>
                      <td>{formatMoney(item.balance)}</td>
                      <td>
                        {!item.fee_plan ? (
                          <span className="status-pill inactive-status">
                            <i />
                            No plan
                          </span>
                        ) : (
                          <span
                            className={`status-pill ${
                              balance <= 0 ? 'active-status' : 'inactive-status'
                            }`}
                          >
                            <i />
                            {balance <= 0 ? 'Paid' : 'Pending'}
                          </span>
                        )}
                      </td>
                      <td>
                        <div className="row-actions">
                          {!item.fee_plan ? (
                            <button onClick={() => openPlan(item)} type="button">
                              Create plan
                            </button>
                          ) : (
                            <button
                              onClick={() => openPayment(item)}
                              disabled={
                                !item.installments.some(
                                  (value) => Number(value.remaining_amount) > 0,
                                )
                              }
                              type="button"
                            >
                              Record payment
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelected(null)
          }}
        >
          <div className="modal-card" role="dialog" aria-modal="true">
            <div className="modal-header">
              <div>
                <span className="eyebrow">FEES · {selected.student_name}</span>
                <h2>{selected.fee_plan ? 'Record payment' : 'Create fee plan'}</h2>
              </div>
              <button className="close-button" onClick={() => setSelected(null)} type="button">
                ×
              </button>
            </div>

            {selected.fee_plan ? (
              <form onSubmit={recordPayment} className="settings-form">
                <div className="fee-plan-summary">
                  <div>
                    <span>Course</span>
                    <strong>{selected.course_name}</strong>
                  </div>
                  <div>
                    <span>Balance</span>
                    <strong>{formatMoney(selected.balance)}</strong>
                  </div>
                  <div>
                    <span>Next due</span>
                    <strong>{nextInstallment ? displayDate(nextInstallment.due_date) : '—'}</strong>
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="fee-installment">Installment</label>
                  <select
                    id="fee-installment"
                    value={paymentForm.installmentId}
                    onChange={(event) => {
                      const installment = selected.installments.find(
                        (value) => String(value.id) === event.target.value,
                      )
                      setPaymentForm({
                        ...paymentForm,
                        installmentId: event.target.value,
                        amount: installment ? String(Number(installment.remaining_amount)) : '',
                      })
                    }}
                    required
                  >
                    {selected.installments
                      .filter((installment) => Number(installment.remaining_amount) > 0)
                      .map((installment) => (
                        <option key={installment.id} value={installment.id}>
                          Installment {installment.installment_number} ·{' '}
                          {formatMoney(installment.remaining_amount)} due ·{' '}
                          {displayDate(installment.due_date)}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="fee-amount">Amount</label>
                  <input
                    id="fee-amount"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={paymentForm.amount}
                    onChange={(event) =>
                      setPaymentForm({ ...paymentForm, amount: event.target.value })
                    }
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="fee-method">Payment method</label>
                  <select
                    id="fee-method"
                    value={paymentForm.method}
                    onChange={(event) =>
                      setPaymentForm({ ...paymentForm, method: event.target.value })
                    }
                  >
                    <option value="cash">Cash</option>
                    <option value="bank_transfer">Bank transfer</option>
                    <option value="upi">UPI</option>
                    <option value="card">Card</option>
                    <option value="cheque">Cheque</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="fee-date">Payment date</label>
                  <input
                    id="fee-date"
                    type="date"
                    value={paymentForm.date}
                    onChange={(event) =>
                      setPaymentForm({ ...paymentForm, date: event.target.value })
                    }
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="fee-reference">Receipt number</label>
                  <input
                    id="fee-reference"
                    value={paymentForm.reference}
                    onChange={(event) =>
                      setPaymentForm({ ...paymentForm, reference: event.target.value })
                    }
                    placeholder="Receipt number (optional)"
                  />
                </div>
                <button className="primary-button" disabled={saving} type="submit">
                  {saving ? 'Saving…' : 'Record payment'}
                </button>
              </form>
            ) : (
              <form onSubmit={createPlan} className="settings-form">
                <div className="fee-plan-summary">
                  <div>
                    <span>Course</span>
                    <strong>{selected.course_name}</strong>
                  </div>
                  <div>
                    <span>Course fee</span>
                    <strong>
                      {Number(selected.course_fee ?? 0) > 0
                        ? formatMoney(selected.course_fee)
                        : 'Not set'}
                    </strong>
                  </div>
                  <div>
                    <span>Admission date</span>
                    <strong>{displayDate(selected.admission_date)}</strong>
                  </div>
                </div>

                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="plan-total">Total course fee</label>
                    <input
                      id="plan-total"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={planForm.total}
                      onChange={(event) => updatePlan({ total: event.target.value })}
                      required
                    />
                    <small className="field-hint">
                      Pre-filled from the course. Adjust it for a negotiated fee.
                    </small>
                  </div>
                  <div className="field">
                    <label htmlFor="plan-discount">Discount</label>
                    <input
                      id="plan-discount"
                      type="number"
                      min="0"
                      step="0.01"
                      value={planForm.discount}
                      onChange={(event) => updatePlan({ discount: event.target.value })}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="plan-scholarship">Scholarship</label>
                    <input
                      id="plan-scholarship"
                      type="number"
                      min="0"
                      step="0.01"
                      value={planForm.scholarship}
                      onChange={(event) => updatePlan({ scholarship: event.target.value })}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="plan-mode">Payment structure</label>
                    <select
                      id="plan-mode"
                      value={planForm.mode}
                      onChange={(event) =>
                        updatePlan({ mode: event.target.value as PaymentMode })
                      }
                    >
                      <option value="one_time">One-time payment</option>
                      <option value="installments">Installments</option>
                    </select>
                  </div>
                  {planForm.mode === 'installments' && (
                    <div className="field">
                      <label htmlFor="plan-count">Number of installments</label>
                      <select
                        id="plan-count"
                        value={planForm.count}
                        onChange={(event) =>
                          updatePlan({ count: Number(event.target.value) })
                        }
                      >
                        {INSTALLMENT_OPTIONS.map((count) => (
                          <option key={count} value={count}>
                            {count} installments
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="plan-first-due">
                      {planForm.mode === 'one_time' ? 'Due date' : 'First installment due'}
                    </label>
                    <input
                      id="plan-first-due"
                      type="date"
                      value={planForm.firstDueDate}
                      onChange={(event) => updatePlan({ firstDueDate: event.target.value })}
                      required
                    />
                    <small className="field-hint">
                      {planForm.mode === 'one_time'
                        ? 'Defaults to today.'
                        : 'Later installments fall on the same day each month.'}
                    </small>
                  </div>
                </div>

                <div className="fee-plan-preview">
                  <div className="fee-plan-preview-head">
                    <span>
                      {planRows.length} {planRows.length === 1 ? 'payment' : 'installments'}
                    </span>
                    <strong>Net payable {formatMoney(netAmount)}</strong>
                  </div>
                  {planRows.length === 0 ? (
                    <p className="field-hint">
                      Enter a total fee greater than the discount and scholarship.
                    </p>
                  ) : (
                    <div className="fee-plan-rows">
                      {planRows.map((row, index) => (
                        <div className="fee-plan-row" key={`${row.dueDate}-${index}`}>
                          <span>
                            {planForm.mode === 'one_time'
                              ? 'One-time payment'
                              : `Installment ${index + 1}`}
                          </span>
                          <strong>{formatMoney(row.amount)}</strong>
                          <span>{displayDate(row.dueDate)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <button className="primary-button" disabled={saving} type="submit">
                  {saving ? 'Creating…' : 'Create fee plan'}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {remindersOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeReminders()
          }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            style={{ maxWidth: '900px' }}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">FEE REMINDERS</span>
                <h2>Send pending fee reminders</h2>
              </div>
              <button className="close-button" onClick={closeReminders} type="button">
                ×
              </button>
            </div>

            <div className="field" style={{ maxWidth: '220px' }}>
              <label htmlFor="reminder-days">Include instalments due within</label>
              <select
                id="reminder-days"
                value={reminderDaysAhead}
                onChange={(event) => {
                  setReminderDaysAhead(event.target.value)
                  void loadReminders(event.target.value)
                }}
              >
                <option value="0">Today only (overdue + today)</option>
                <option value="7">Next 7 days</option>
                <option value="15">Next 15 days</option>
                <option value="30">Next 30 days</option>
                <option value="60">Next 60 days</option>
                <option value="90">Next 90 days</option>
              </select>
              <small className="field-hint">
                Reminders are sent only when you confirm — nothing is emailed automatically.
              </small>
            </div>

            {remindersLoading ? (
              <div className="table-state">Loading pending instalments…</div>
            ) : reminders.length === 0 ? (
              <div className="table-state">
                <strong>No pending instalments</strong>
                <p>Every instalment in this window is already paid for your branch.</p>
              </div>
            ) : (
              <div className="table-wrap" style={{ marginTop: '14px' }}>
                <table>
                  <thead>
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Select all instalments with a contact"
                          checked={
                            reminderSelection.length > 0 &&
                            reminderSelection.length ===
                              reminders.filter((row) => row.email || row.phone).length
                          }
                          onChange={toggleAllReminders}
                        />
                      </th>
                      <th>Student</th>
                      <th>Course / batch</th>
                      <th>Instalment</th>
                      <th>Pending</th>
                      <th>Due</th>
                      <th>Status</th>
                      <th>Email</th>
                      <th>Phone</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reminders.map((row) => (
                      <tr key={row.installment_id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Select ${row.student_name} instalment ${row.installment_number}`}
                            disabled={!row.email && !row.phone}
                            checked={reminderSelection.includes(row.installment_id)}
                            onChange={() => toggleReminder(row.installment_id)}
                          />
                        </td>
                        <td>
                          <strong>{row.student_name}</strong>
                          <small>{row.student_code}</small>
                        </td>
                        <td>
                          {row.course_name}
                          <small>{row.batch_name}</small>
                        </td>
                        <td>#{row.installment_number}</td>
                        <td>{formatMoney(row.remaining_amount)}</td>
                        <td>{displayDate(row.due_date)}</td>
                        <td>
                          <span
                            className={`status-pill ${
                              row.status === 'Overdue' ? 'inactive-status' : 'active-status'
                            }`}
                          >
                            <i />
                            {row.status}
                          </span>
                        </td>
                        <td>{row.email ?? 'No email'}</td>
                        <td>{row.phone ?? 'No phone'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {reminderResult && (
              <div className="success-message" style={{ marginTop: '14px' }}>
                Email — Sent {reminderResult.sent_count} · Skipped {reminderResult.skipped_count} ·
                Failed {reminderResult.failed_count}
                {reminderResult.failed.length > 0 && (
                  <span> — failed: {reminderResult.failed.join(', ')}</span>
                )}
                {reminderResult.skipped.length > 0 && (
                  <span> — skipped: {reminderResult.skipped.join(', ')}</span>
                )}
              </div>
            )}
            {whatsAppReminderResult && (
              <div className="success-message" style={{ marginTop: '14px' }}>
                WhatsApp — Sent {whatsAppReminderResult.sent_count} · Skipped{' '}
                {whatsAppReminderResult.skipped_count} · Failed{' '}
                {whatsAppReminderResult.failed_count}
                {whatsAppReminderResult.failed.length > 0 && (
                  <span> — failed: {whatsAppReminderResult.failed.join(', ')}</span>
                )}
                {whatsAppReminderResult.skipped.length > 0 && (
                  <span> — skipped: {whatsAppReminderResult.skipped.join(', ')}</span>
                )}
              </div>
            )}

            <div className="modal-actions">
              <button className="secondary-button" onClick={closeReminders} type="button">
                Close
              </button>
              <button
                className="secondary-button"
                disabled={sendingWhatsAppReminders || reminderSelection.length === 0}
                onClick={() => void sendWhatsAppReminders()}
                type="button"
              >
                {sendingWhatsAppReminders
                  ? 'Sending…'
                  : `WhatsApp ${reminderSelection.length || ''}`}
              </button>
              <button
                className="primary-button"
                disabled={sendingReminders || reminderSelection.length === 0}
                onClick={() => void sendReminders()}
                type="button"
              >
                {sendingReminders
                  ? 'Sending…'
                  : `Email ${reminderSelection.length || ''} reminder${
                      reminderSelection.length === 1 ? '' : 's'
                    }`}
              </button>
            </div>
          </div>
        </div>
      )}

      {receipt && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card receipt-card" role="dialog" aria-modal="true">
            <div className="receipt-content">
              <span className="eyebrow">PAYMENT RECEIPT</span>
              <h2>{receipt.branch_name}</h2>
              <p>
                {receipt.branch_address || ''}
                {receipt.branch_phone ? ` · ${receipt.branch_phone}` : ''}
              </p>
              <hr />
              <div className="receipt-grid">
                <span>Receipt number</span>
                <strong>{receipt.receipt_number}</strong>
                <span>Student</span>
                <strong>
                  {receipt.student_name} ({receipt.student_code})
                </strong>
                <span>Course / batch</span>
                <strong>
                  {receipt.course_name} / {receipt.batch_name}
                </strong>
                <span>Installment</span>
                <strong>{receipt.installment_number}</strong>
                <span>Amount paid</span>
                <strong>{formatMoney(receipt.amount)}</strong>
                <span>Payment method</span>
                <strong>{receipt.payment_method.replace('_', ' ')}</strong>
                <span>Payment date</span>
                <strong>{receipt.payment_date}</strong>
                <span>Remaining balance</span>
                <strong>{formatMoney(receipt.balance)}</strong>
                {receipt.student_email && (
                  <>
                    <span>Student email</span>
                    <strong>{receipt.student_email}</strong>
                  </>
                )}
              </div>
            </div>
            {receiptEmailMessage && (
              <p className="field-hint receipt-email-note">{receiptEmailMessage}</p>
            )}
            {receiptWhatsAppMessage && (
              <p className="field-hint receipt-email-note">{receiptWhatsAppMessage}</p>
            )}
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => window.print()} type="button">
                Print receipt
              </button>
              <button
                className="secondary-button"
                disabled={emailingReceipt || !receiptPaymentId}
                onClick={() => void emailReceipt()}
                type="button"
              >
                {emailingReceipt ? 'Emailing…' : 'Email receipt'}
              </button>
              <button
                className="secondary-button"
                disabled={whatsappingReceipt || !receiptPaymentId}
                onClick={() => void whatsappReceipt()}
                type="button"
              >
                {whatsappingReceipt ? 'Sending…' : 'WhatsApp receipt'}
              </button>
              <button className="primary-button" onClick={closeReceipt} type="button">
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default FeesPage
