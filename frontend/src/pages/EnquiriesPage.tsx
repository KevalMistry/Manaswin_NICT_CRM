import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import type { Enquiry, EnquirySource, EnquiryStatus } from '../types'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser, hasModuleAccess } from '../utils/auth'
import { todayInputValue } from '../utils/date'

type Branch = { id: number; name: string; code: string }
type Course = { id: number; name: string; is_active: boolean }
type Batch = {
  id: number
  name: string
  code: string
  course_id: number
  branch_id: number
  capacity: number
  is_active: boolean
}
type Student = {
  id: number
  full_name: string
  student_code: string
  branch_id: number
  is_active: boolean
}

type EnquiryForm = {
  full_name: string
  phone: string
  email: string
  branch_id: string
  course_id: string
  source: EnquirySource
  status: string
  follow_up_date: string
  notes: string
}

const STATUS_ORDER: EnquiryStatus[] = [
  'new_lead',
  'follow_up',
  'demo',
  'counselling',
  'admitted',
  'lost',
]

const STATUS_LABELS: Record<EnquiryStatus, string> = {
  new_lead: 'New lead',
  follow_up: 'Follow up',
  demo: 'Demo',
  counselling: 'Counselling',
  admitted: 'Admitted',
  lost: 'Lost',
}

const SOURCE_LABELS: Record<EnquirySource, string> = {
  walk_in: 'Walk-in',
  online: 'Online',
  website: 'Website',
  whatsapp: 'WhatsApp',
  facebook: 'Facebook',
  google_ads: 'Google Ads',
  referral: 'Referral',
  other: 'Other',
}

const NEXT_STATUS: Partial<Record<EnquiryStatus, EnquiryStatus>> = {
  new_lead: 'follow_up',
  follow_up: 'demo',
  demo: 'counselling',
}

const OPEN_STATUSES: EnquiryStatus[] = ['new_lead', 'follow_up', 'demo', 'counselling']

const emptyForm: EnquiryForm = {
  full_name: '',
  phone: '',
  email: '',
  branch_id: '',
  course_id: '',
  source: 'walk_in',
  status: 'new_lead',
  follow_up_date: '',
  notes: '',
}

function EnquiriesPage() {
  const [enquiries, setEnquiries] = useState<Enquiry[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [courses, setCourses] = useState<Course[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [students, setStudents] = useState<Student[]>([])

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | EnquiryStatus>('all')
  const [sourceFilter, setSourceFilter] = useState<'all' | EnquirySource>('all')

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<EnquiryForm>(emptyForm)
  const [isSaving, setIsSaving] = useState(false)

  const [converting, setConverting] = useState<Enquiry | null>(null)
  const [convertForm, setConvertForm] = useState({
    batch_id: '',
    admission_date: todayInputValue(),
    student_id: '',
  })
  const [isConverting, setIsConverting] = useState(false)

  const currentUser = getStoredUser()
  const roleName = currentUser?.role_name ?? ''
  const isSuperAdmin = roleName === 'Super Admin'
  const canManage =
    hasModuleAccess(currentUser, 'enquiries') &&
    ['Super Admin', 'Branch Admin', 'Counsellor'].includes(roleName)
  const followUpCutoff = todayInputValue()

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const [enquiryResponse, branchResponse, courseResponse, batchResponse, studentResponse] =
        await Promise.all([
          api.get<Enquiry[]>('/api/enquiries'),
          api.get<Branch[]>('/api/branches'),
          api.get<Course[]>('/api/courses', { params: { include_inactive: true, limit: 100 } }),
          api.get<Batch[]>('/api/batches', { params: { include_inactive: true, limit: 100 } }),
          api
            .get<Student[]>('/api/students', { params: { include_inactive: true, limit: 100 } })
            .then((response) => response.data)
            .catch(() => [] as Student[]),
        ])
      setEnquiries(enquiryResponse.data)
      setBranches(branchResponse.data)
      setCourses(courseResponse.data)
      setBatches(batchResponse.data)
      setStudents(studentResponse)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not load the enquiry pipeline.'))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const branchName = (id: number) => branches.find((branch) => branch.id === id)?.name ?? `Branch #${id}`
  const courseName = (id: number | null) =>
    id === null ? 'Not selected' : courses.find((course) => course.id === id)?.name ?? `Course #${id}`
  const studentName = (id: number | null) =>
    id === null ? null : students.find((student) => student.id === id)?.full_name ?? `Student #${id}`

  const counts = useMemo(() => {
    const result: Record<string, number> = { all: enquiries.length }
    for (const status of STATUS_ORDER) {
      result[status] = enquiries.filter((enquiry) => enquiry.status === status).length
    }
    return result
  }, [enquiries])

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    return enquiries.filter((enquiry) => {
      const matchesStatus = statusFilter === 'all' || enquiry.status === statusFilter
      const matchesSource = sourceFilter === 'all' || enquiry.source === sourceFilter
      const text = [
        enquiry.full_name,
        enquiry.enquiry_code,
        enquiry.phone ?? '',
        enquiry.email ?? '',
        courses.find((course) => course.id === enquiry.course_id)?.name ?? '',
      ]
        .join(' ')
        .toLowerCase()
      return matchesStatus && matchesSource && (!term || text.includes(term))
    })
  }, [enquiries, search, statusFilter, sourceFilter, courses])

  function openCreate() {
    setEditingId(null)
    setForm({
      ...emptyForm,
      branch_id: String(currentUser?.branch_id ?? branches[0]?.id ?? ''),
      follow_up_date: todayInputValue(),
    })
    setError('')
    setMessage('')
    setIsFormOpen(true)
  }

  function openEdit(enquiry: Enquiry) {
    setEditingId(enquiry.id)
    setForm({
      full_name: enquiry.full_name,
      phone: enquiry.phone ?? '',
      email: enquiry.email ?? '',
      branch_id: String(enquiry.branch_id),
      course_id: enquiry.course_id ? String(enquiry.course_id) : '',
      source: enquiry.source,
      status: enquiry.status,
      follow_up_date: enquiry.follow_up_date ?? '',
      notes: enquiry.notes ?? '',
    })
    setError('')
    setMessage('')
    setIsFormOpen(true)
  }

  function updateField(field: keyof EnquiryForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    setMessage('')
    const payload = {
      full_name: form.full_name,
      phone: form.phone || null,
      email: form.email || null,
      branch_id: Number(form.branch_id),
      course_id: form.course_id ? Number(form.course_id) : null,
      source: form.source,
      follow_up_date: form.follow_up_date || null,
      notes: form.notes || null,
    }
    try {
      if (editingId) {
        await api.patch(`/api/enquiries/${editingId}`, { ...payload, status: form.status })
        setMessage('Enquiry updated.')
      } else {
        await api.post('/api/enquiries', payload)
        setMessage('Enquiry created and added to the pipeline.')
      }
      setIsFormOpen(false)
      await loadData()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to save this enquiry.'))
    } finally {
      setIsSaving(false)
    }
  }

  async function advanceStatus(enquiry: Enquiry) {
    const next = NEXT_STATUS[enquiry.status]
    if (!next) return
    await changeStatus(enquiry, next, `Move ${enquiry.full_name} to ${STATUS_LABELS[next]}?`)
  }

  async function changeStatus(enquiry: Enquiry, status: EnquiryStatus, confirmText: string) {
    if (!window.confirm(confirmText)) return
    setError('')
    setMessage('')
    try {
      await api.patch(`/api/enquiries/${enquiry.id}`, { status })
      setMessage(`${enquiry.full_name} moved to ${STATUS_LABELS[status]}.`)
      await loadData()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to update the enquiry status.'))
    }
  }

  function openConvert(enquiry: Enquiry) {
    setConverting(enquiry)
    setConvertForm({
      batch_id: '',
      admission_date: todayInputValue(),
      student_id: '',
    })
    setError('')
    setMessage('')
  }

  async function submitConversion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!converting) return
    setIsConverting(true)
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<{
        student: { full_name: string; student_code: string }
        enrollment: { enrollment_code: string }
      }>(`/api/enquiries/${converting.id}/convert`, {
        batch_id: Number(convertForm.batch_id),
        admission_date: convertForm.admission_date,
        student_id: convertForm.student_id ? Number(convertForm.student_id) : null,
      })
      setMessage(
        `Admission complete: ${data.student.full_name} (${data.student.student_code}) · ${data.enrollment.enrollment_code}`,
      )
      setConverting(null)
      await loadData()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to convert this enquiry into an admission.'))
    } finally {
      setIsConverting(false)
    }
  }

  const convertingBatches = converting
    ? batches.filter(
        (batch) =>
          batch.is_active &&
          batch.branch_id === converting.branch_id &&
          (converting.course_id === null || batch.course_id === converting.course_id),
      )
    : []
  const convertibleBatches = convertingBatches.length
    ? convertingBatches
    : converting
      ? batches.filter((batch) => batch.is_active && batch.branch_id === converting.branch_id)
      : []
  const linkableStudents = converting
    ? students.filter(
        (student) => student.is_active && student.branch_id === converting.branch_id,
      )
    : []

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">CRM · ENQUIRY TO ADMISSION</span>
          <h1>Enquiries</h1>
          <p>Track leads from first contact through counselling and convert them into admissions.</p>
        </div>
        {canManage && (
          <button className="primary-button" onClick={openCreate} type="button">
            + New enquiry
          </button>
        )}
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="module-tabs enquiry-tabs" aria-label="Enquiry pipeline">
        <button
          className={statusFilter === 'all' ? 'active-tab' : ''}
          onClick={() => setStatusFilter('all')}
          type="button"
        >
          All <span>{counts.all}</span>
        </button>
        {STATUS_ORDER.map((status) => (
          <button
            className={statusFilter === status ? 'active-tab' : ''}
            key={status}
            onClick={() => setStatusFilter(status)}
            type="button"
          >
            {STATUS_LABELS[status]} <span>{counts[status] ?? 0}</span>
          </button>
        ))}
      </section>

      <section className="module-toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input
            aria-label="Search enquiries"
            placeholder="Search name, phone, email or enquiry ID…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="toolbar-controls">
          <select
            aria-label="Filter enquiry source"
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value as 'all' | EnquirySource)}
          >
            <option value="all">All sources</option>
            {(Object.keys(SOURCE_LABELS) as EnquirySource[]).map((source) => (
              <option key={source} value={source}>
                {SOURCE_LABELS[source]}
              </option>
            ))}
          </select>
          <span className="result-count">{visible.length} enquiries</span>
        </div>
      </section>

      <section className="data-panel">
        {isLoading ? (
          <div className="table-state">Loading enquiries…</div>
        ) : visible.length === 0 ? (
          <div className="table-state">
            <div className="empty-icon">☎</div>
            <strong>{search || statusFilter !== 'all' || sourceFilter !== 'all' ? 'No matching enquiries' : 'No enquiries yet'}</strong>
            <p>
              {search || statusFilter !== 'all' || sourceFilter !== 'all'
                ? 'Try another filter or search term.'
                : 'Capture a walk-in, phone or online lead to start the admission pipeline.'}
            </p>
            {!search && statusFilter === 'all' && sourceFilter === 'all' && canManage && (
              <button className="primary-button" onClick={openCreate} type="button">
                Create first enquiry
              </button>
            )}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Enquiry</th>
                  <th>Contact</th>
                  <th>Interested course</th>
                  <th>Source</th>
                  <th>Follow-up</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((enquiry) => {
                  const next = NEXT_STATUS[enquiry.status]
                  const overdue =
                    OPEN_STATUSES.includes(enquiry.status) &&
                    enquiry.follow_up_date !== null &&
                    enquiry.follow_up_date < followUpCutoff
                  const admittedStudent = studentName(enquiry.student_id)
                  return (
                    <tr key={enquiry.id}>
                      <td>
                        <div className="branch-name">
                          <span className="branch-avatar">{enquiry.full_name.slice(0, 1).toUpperCase()}</span>
                          <span>
                            <strong>{enquiry.full_name}</strong>
                            <small>{enquiry.enquiry_code} · {branchName(enquiry.branch_id)}</small>
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className="contact-cell">
                          {enquiry.phone || '—'}
                          {enquiry.email ? ` · ${enquiry.email}` : ''}
                        </span>
                      </td>
                      <td>{courseName(enquiry.course_id)}</td>
                      <td>{SOURCE_LABELS[enquiry.source]}</td>
                      <td>
                        {enquiry.follow_up_date ? (
                          <span className={overdue ? 'overdue-date' : ''}>
                            {enquiry.follow_up_date}
                            {overdue ? ' · overdue' : ''}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        <span className={`status-pill pipeline-${enquiry.status}`}>
                          <i />
                          {STATUS_LABELS[enquiry.status]}
                        </span>
                        {admittedStudent && <small className="muted-block">{admittedStudent}</small>}
                      </td>
                      <td>
                        <div className="row-actions enquiry-actions">
                          {next && canManage && (
                            <button onClick={() => void advanceStatus(enquiry)} type="button">
                              → {STATUS_LABELS[next]}
                            </button>
                          )}
                          {OPEN_STATUSES.includes(enquiry.status) && canManage && (
                            <button onClick={() => openConvert(enquiry)} type="button">
                              Convert
                            </button>
                          )}
                          {OPEN_STATUSES.includes(enquiry.status) && canManage && (
                            <button
                              className="danger-action"
                              onClick={() =>
                                void changeStatus(
                                  enquiry,
                                  'lost',
                                  `Mark ${enquiry.full_name} as lost?`,
                                )
                              }
                              type="button"
                            >
                              Lost
                            </button>
                          )}
                          {enquiry.status !== 'admitted' && canManage && (
                            <button onClick={() => openEdit(enquiry)} type="button">
                              Edit
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

      {isFormOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setIsFormOpen(false)
          }}
        >
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="enquiry-modal-title">
            <div className="modal-header">
              <div>
                <span className="eyebrow">{editingId ? 'UPDATE ENQUIRY' : 'NEW ENQUIRY'}</span>
                <h2 id="enquiry-modal-title">{editingId ? 'Update enquiry' : 'Capture an enquiry'}</h2>
              </div>
              <button className="close-button" onClick={() => setIsFormOpen(false)} type="button">
                ×
              </button>
            </div>
            <form onSubmit={submit}>
              <div className="form-grid">
                <div className="field full-field">
                  <label htmlFor="enquiry-name">Full name</label>
                  <input
                    id="enquiry-name"
                    value={form.full_name}
                    onChange={(event) => updateField('full_name', event.target.value)}
                    placeholder="Prospective student name"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="enquiry-phone">Phone</label>
                  <input
                    id="enquiry-phone"
                    value={form.phone}
                    onChange={(event) => updateField('phone', event.target.value)}
                    placeholder="+91…"
                  />
                </div>
                <div className="field">
                  <label htmlFor="enquiry-email">Email</label>
                  <input
                    id="enquiry-email"
                    type="email"
                    value={form.email}
                    onChange={(event) => updateField('email', event.target.value)}
                    placeholder="lead@example.com"
                  />
                </div>
                <div className="field">
                  <label htmlFor="enquiry-branch">Branch</label>
                  <select
                    id="enquiry-branch"
                    value={form.branch_id}
                    onChange={(event) => updateField('branch_id', event.target.value)}
                    disabled={!isSuperAdmin}
                    required
                  >
                    <option value="">Select branch</option>
                    {branches.map((branch) => (
                      <option key={branch.id} value={branch.id}>
                        {branch.name} ({branch.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="enquiry-course">Interested course</label>
                  <select
                    id="enquiry-course"
                    value={form.course_id}
                    onChange={(event) => updateField('course_id', event.target.value)}
                  >
                    <option value="">Not selected</option>
                    {courses
                      .filter((course) => course.is_active)
                      .map((course) => (
                        <option key={course.id} value={course.id}>
                          {course.name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="enquiry-source">Lead source</label>
                  <select
                    id="enquiry-source"
                    value={form.source}
                    onChange={(event) => updateField('source', event.target.value)}
                  >
                    {(Object.keys(SOURCE_LABELS) as EnquirySource[]).map((source) => (
                      <option key={source} value={source}>
                        {SOURCE_LABELS[source]}
                      </option>
                    ))}
                  </select>
                </div>
                {editingId && (
                  <div className="field">
                    <label htmlFor="enquiry-status">Pipeline stage</label>
                    <select
                      id="enquiry-status"
                      value={form.status}
                      onChange={(event) => updateField('status', event.target.value)}
                    >
                      {STATUS_ORDER.filter((status) => status !== 'admitted').map((status) => (
                        <option key={status} value={status}>
                          {STATUS_LABELS[status]}
                        </option>
                      ))}
                    </select>
                    <small className="field-hint">Use “Convert” to reach the admitted stage.</small>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="enquiry-followup">Next follow-up</label>
                  <input
                    id="enquiry-followup"
                    type="date"
                    value={form.follow_up_date}
                    onChange={(event) => updateField('follow_up_date', event.target.value)}
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="enquiry-notes">Notes</label>
                  <textarea
                    id="enquiry-notes"
                    rows={3}
                    value={form.notes}
                    onChange={(event) => updateField('notes', event.target.value)}
                    placeholder="Counselling notes, callback details, demo schedule…"
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isSaving} type="submit">
                  {isSaving ? 'Saving…' : editingId ? 'Save changes' : 'Create enquiry'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {converting && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setConverting(null)
          }}
        >
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="convert-modal-title">
            <div className="modal-header">
              <div>
                <span className="eyebrow">CONVERT TO ADMISSION</span>
                <h2 id="convert-modal-title">{converting.full_name}</h2>
              </div>
              <button className="close-button" onClick={() => setConverting(null)} type="button">
                ×
              </button>
            </div>
            <form onSubmit={submitConversion}>
              <div className="form-grid">
                <div className="field full-field">
                  <label htmlFor="convert-batch">Batch</label>
                  <select
                    id="convert-batch"
                    value={convertForm.batch_id}
                    onChange={(event) =>
                      setConvertForm((current) => ({ ...current, batch_id: event.target.value }))
                    }
                    required
                  >
                    <option value="">Select active batch</option>
                    {convertibleBatches.map((batch) => (
                      <option key={batch.id} value={batch.id}>
                        {batch.name} ({batch.code}) · capacity {batch.capacity}
                      </option>
                    ))}
                  </select>
                  {!convertibleBatches.length && (
                    <small className="field-hint">
                      This branch has no active batch for the selected course. Create a batch first.
                    </small>
                  )}
                </div>
                <div className="field">
                  <label htmlFor="convert-date">Admission date</label>
                  <input
                    id="convert-date"
                    type="date"
                    value={convertForm.admission_date}
                    onChange={(event) =>
                      setConvertForm((current) => ({ ...current, admission_date: event.target.value }))
                    }
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="convert-student">Student record</label>
                  <select
                    id="convert-student"
                    value={convertForm.student_id}
                    onChange={(event) =>
                      setConvertForm((current) => ({ ...current, student_id: event.target.value }))
                    }
                  >
                    <option value="">Create a new student from this enquiry</option>
                    {linkableStudents.map((student) => (
                      <option key={student.id} value={student.id}>
                        {student.full_name} ({student.student_code})
                      </option>
                    ))}
                  </select>
                  <small className="field-hint">
                    Link an existing student if this lead already has a student profile.
                  </small>
                </div>
              </div>
              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setConverting(null)} type="button">
                  Cancel
                </button>
                <button
                  className="primary-button"
                  disabled={isConverting || !convertForm.batch_id || !convertibleBatches.length}
                  type="submit"
                >
                  {isConverting ? 'Admitting…' : 'Convert to admission'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

export default EnquiriesPage
