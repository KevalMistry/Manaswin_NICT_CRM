import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'

type Company = {
  id: number
  name: string
  industry: string | null
  website: string | null
  location: string | null
  contact_person: string | null
  contact_email: string | null
  contact_phone: string | null
  notes: string | null
  is_active: boolean
  openings_count: number
  created_at: string
}

type Opening = {
  id: number
  company_id: number
  company_name: string
  title: string
  description: string | null
  location: string | null
  employment_type: string
  work_mode: string
  salary_min: string | null
  salary_max: string | null
  vacancies: number
  last_date: string | null
  status: string
  branch_id: number | null
  branch_name: string | null
  course_ids: number[]
  course_names: string[]
  applications_count: number
  created_at: string
}

type Application = {
  id: number
  job_opening_id: number
  opening_title: string
  company_name: string
  student_id: number
  student_name: string
  student_code: string
  branch_id: number
  branch_name: string
  course_names: string[]
  status: string
  source: string
  resume_url: string | null
  cover_note: string | null
  interview_date: string | null
  interview_mode: string | null
  interview_location: string | null
  feedback: string | null
  offer_salary: string | null
  offer_date: string | null
  joining_date: string | null
  offer_letter_url: string | null
  applied_at: string
  updated_at: string
}

type Summary = {
  companies: number
  open_openings: number
  total_applications: number
  by_status: Record<string, number>
  offers_released: number
  joined: number
}

type CourseOption = { id: number; name: string; code: string }
type StudentOption = { id: number; student_code: string; full_name: string }

const STATUSES = [
  'applied',
  'shortlisted',
  'interview_scheduled',
  'selected',
  'offer_released',
  'joined',
  'rejected',
  'withdrawn',
] as const

const EMPLOYMENT_TYPES = ['Full-time', 'Internship', 'Part-time', 'Contract']
const WORK_MODES = ['On-site', 'Remote', 'Hybrid']
const INTERVIEW_MODES = ['On-site', 'Phone', 'Video']

function statusLabel(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatSalary(min: string | null, max: string | null): string {
  if (!min && !max) return 'Not disclosed'
  const left = min ? `₹${Number(min).toLocaleString('en-IN')}` : ''
  const right = max ? `₹${Number(max).toLocaleString('en-IN')}` : ''
  return left && right ? `${left} – ${right}` : left || right
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function PlacementPage() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [openings, setOpenings] = useState<Opening[]>([])
  const [applications, setApplications] = useState<Application[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [courses, setCourses] = useState<CourseOption[]>([])
  const [students, setStudents] = useState<StudentOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')

  const [companyForm, setCompanyForm] = useState({
    name: '',
    industry: '',
    location: '',
    contact_person: '',
    contact_email: '',
    contact_phone: '',
  })
  const [openingForm, setOpeningForm] = useState({
    company_id: '',
    title: '',
    description: '',
    location: '',
    employment_type: 'Full-time',
    work_mode: 'On-site',
    salary_min: '',
    salary_max: '',
    vacancies: '1',
    last_date: '',
  })
  const [openingCourseIds, setOpeningCourseIds] = useState<number[]>([])

  const [statusFilter, setStatusFilter] = useState('all')
  const [applicationSearch, setApplicationSearch] = useState('')
  const [showAddApplication, setShowAddApplication] = useState(false)
  const [addForm, setAddForm] = useState({
    job_opening_id: '',
    student_id: '',
    resume_url: '',
    cover_note: '',
  })
  const [editing, setEditing] = useState<Application | null>(null)
  const [editForm, setEditForm] = useState({
    status: 'applied',
    interview_date: '',
    interview_mode: '',
    interview_location: '',
    feedback: '',
    offer_salary: '',
    offer_date: '',
    joining_date: '',
    offer_letter_url: '',
  })

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [companyRes, openingRes, applicationRes, summaryRes, courseRes, studentRes] =
        await Promise.all([
          api.get<Company[]>('/api/placement/companies'),
          api.get<Opening[]>('/api/placement/openings'),
          api.get<Application[]>('/api/placement/applications'),
          api.get<Summary>('/api/placement/summary'),
          api.get<CourseOption[]>('/api/courses'),
          api.get<StudentOption[]>('/api/students'),
        ])
      setCompanies(companyRes.data)
      setOpenings(openingRes.data)
      setApplications(applicationRes.data)
      setSummary(summaryRes.data)
      setCourses(courseRes.data.filter((course) => course.id > 0))
      setStudents(studentRes.data.filter((student) => student.id > 0))
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the placement cell.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const filteredApplications = useMemo(() => {
    const search = applicationSearch.trim().toLowerCase()
    return applications.filter((application) => {
      if (statusFilter !== 'all' && application.status !== statusFilter) return false
      if (!search) return true
      return [
        application.student_name,
        application.student_code,
        application.company_name,
        application.opening_title,
      ]
        .join(' ')
        .toLowerCase()
        .includes(search)
    })
  }, [applications, statusFilter, applicationSearch])

  const activeCompanies = useMemo(
    () => companies.filter((company) => company.is_active),
    [companies],
  )

  function flash(text: string) {
    setMessage(text)
    setError('')
  }

  function fail(requestError: unknown, fallback: string) {
    setError(apiErrorMessage(requestError, fallback))
    setMessage('')
  }

  async function createCompany(event: React.FormEvent) {
    event.preventDefault()
    setBusy('company')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Company>('/api/placement/companies', {
        name: companyForm.name.trim(),
        industry: companyForm.industry.trim() || null,
        location: companyForm.location.trim() || null,
        contact_person: companyForm.contact_person.trim() || null,
        contact_email: companyForm.contact_email.trim() || null,
        contact_phone: companyForm.contact_phone.trim() || null,
      })
      setCompanies((current) => [...current, data].sort((a, b) => a.name.localeCompare(b.name)))
      setCompanyForm({
        name: '',
        industry: '',
        location: '',
        contact_person: '',
        contact_email: '',
        contact_phone: '',
      })
      flash(`${data.name} added to the company database.`)
    } catch (requestError) {
      fail(requestError, 'Unable to save the company.')
    } finally {
      setBusy('')
    }
  }

  async function toggleCompany(company: Company) {
    setBusy(`company-${company.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Company>(`/api/placement/companies/${company.id}`, {
        is_active: !company.is_active,
      })
      setCompanies((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      flash(`${data.name} is now ${data.is_active ? 'active' : 'inactive'}.`)
    } catch (requestError) {
      fail(requestError, 'Unable to update the company.')
    } finally {
      setBusy('')
    }
  }

  async function deleteCompany(company: Company) {
    if (!window.confirm(`Delete ${company.name} from the company database?`)) return
    setBusy(`company-${company.id}`)
    setError('')
    setMessage('')
    try {
      await api.delete(`/api/placement/companies/${company.id}`)
      setCompanies((current) => current.filter((item) => item.id !== company.id))
      flash(`${company.name} removed.`)
    } catch (requestError) {
      fail(requestError, 'Unable to delete the company.')
    } finally {
      setBusy('')
    }
  }

  async function createOpening(event: React.FormEvent) {
    event.preventDefault()
    if (!openingForm.company_id) {
      setError('Choose a company for this opening.')
      return
    }
    setBusy('opening')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Opening>('/api/placement/openings', {
        company_id: Number(openingForm.company_id),
        title: openingForm.title.trim(),
        description: openingForm.description.trim() || null,
        location: openingForm.location.trim() || null,
        employment_type: openingForm.employment_type,
        work_mode: openingForm.work_mode,
        salary_min: openingForm.salary_min || null,
        salary_max: openingForm.salary_max || null,
        vacancies: Number(openingForm.vacancies) || 1,
        last_date: openingForm.last_date || null,
        course_ids: openingCourseIds,
      })
      setOpenings((current) => [data, ...current])
      setOpeningForm({
        company_id: openingForm.company_id,
        title: '',
        description: '',
        location: '',
        employment_type: 'Full-time',
        work_mode: 'On-site',
        salary_min: '',
        salary_max: '',
        vacancies: '1',
        last_date: '',
      })
      setOpeningCourseIds([])
      flash(`${data.title} is now open for applications.`)
      const summaryRes = await api.get<Summary>('/api/placement/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to publish the job opening.')
    } finally {
      setBusy('')
    }
  }

  async function toggleOpening(opening: Opening) {
    setBusy(`opening-${opening.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Opening>(`/api/placement/openings/${opening.id}`, {
        status: opening.status === 'open' ? 'closed' : 'open',
      })
      setOpenings((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      flash(`${data.title} is now ${data.status}.`)
    } catch (requestError) {
      fail(requestError, 'Unable to update the opening.')
    } finally {
      setBusy('')
    }
  }

  async function deleteOpening(opening: Opening) {
    if (!window.confirm(`Delete the opening “${opening.title}”?`)) return
    setBusy(`opening-${opening.id}`)
    setError('')
    setMessage('')
    try {
      await api.delete(`/api/placement/openings/${opening.id}`)
      setOpenings((current) => current.filter((item) => item.id !== opening.id))
      flash(`${opening.title} removed.`)
    } catch (requestError) {
      fail(requestError, 'Unable to delete the opening.')
    } finally {
      setBusy('')
    }
  }

  function toggleCourse(courseId: number) {
    setOpeningCourseIds((current) =>
      current.includes(courseId)
        ? current.filter((id) => id !== courseId)
        : [...current, courseId],
    )
  }

  async function addApplication(event: React.FormEvent) {
    event.preventDefault()
    if (!addForm.job_opening_id || !addForm.student_id) {
      setError('Choose both a job opening and a student.')
      return
    }
    setBusy('application')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Application>('/api/placement/applications', {
        job_opening_id: Number(addForm.job_opening_id),
        student_id: Number(addForm.student_id),
        resume_url: addForm.resume_url.trim() || null,
        cover_note: addForm.cover_note.trim() || null,
      })
      setApplications((current) => [data, ...current])
      setShowAddApplication(false)
      setAddForm({ job_opening_id: '', student_id: '', resume_url: '', cover_note: '' })
      flash(`${data.student_name} added to ${data.opening_title}.`)
      const [summaryRes, openingRes] = await Promise.all([
        api.get<Summary>('/api/placement/summary'),
        api.get<Opening[]>('/api/placement/openings'),
      ])
      setSummary(summaryRes.data)
      setOpenings(openingRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to add the application.')
    } finally {
      setBusy('')
    }
  }

  async function quickStatus(application: Application, status: string) {
    setBusy(`application-${application.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Application>(
        `/api/placement/applications/${application.id}`,
        { status },
      )
      setApplications((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      flash(`${data.student_name} moved to ${statusLabel(status)}.`)
      const summaryRes = await api.get<Summary>('/api/placement/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to update the application.')
    } finally {
      setBusy('')
    }
  }

  function openEditor(application: Application) {
    setEditing(application)
    setEditForm({
      status: application.status,
      interview_date: application.interview_date?.slice(0, 16) ?? '',
      interview_mode: application.interview_mode ?? '',
      interview_location: application.interview_location ?? '',
      feedback: application.feedback ?? '',
      offer_salary: application.offer_salary ?? '',
      offer_date: application.offer_date ?? '',
      joining_date: application.joining_date ?? '',
      offer_letter_url: application.offer_letter_url ?? '',
    })
    setError('')
  }

  async function saveApplication(event: React.FormEvent) {
    event.preventDefault()
    if (!editing) return
    setBusy(`application-${editing.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Application>(
        `/api/placement/applications/${editing.id}`,
        {
          status: editForm.status,
          interview_date: editForm.interview_date || null,
          interview_mode: editForm.interview_mode || null,
          interview_location: editForm.interview_location.trim() || null,
          feedback: editForm.feedback.trim() || null,
          offer_salary: editForm.offer_salary || null,
          offer_date: editForm.offer_date || null,
          joining_date: editForm.joining_date || null,
          offer_letter_url: editForm.offer_letter_url.trim() || null,
        },
      )
      setApplications((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      setEditing(null)
      flash(`${data.student_name}'s placement record updated.`)
      const summaryRes = await api.get<Summary>('/api/placement/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to save the placement record.')
    } finally {
      setBusy('')
    }
  }

  async function deleteApplication(application: Application) {
    if (
      !window.confirm(
        `Remove ${application.student_name}'s application for ${application.opening_title}?`,
      )
    ) {
      return
    }
    setBusy(`application-${application.id}`)
    setError('')
    setMessage('')
    try {
      await api.delete(`/api/placement/applications/${application.id}`)
      setApplications((current) => current.filter((item) => item.id !== application.id))
      flash('Application removed.')
      const summaryRes = await api.get<Summary>('/api/placement/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to remove the application.')
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">PLACEMENT CELL</span>
          <h1>Companies, openings and offers</h1>
          <p>
            Maintain the hiring partner database, publish course-eligible openings
            and track every student from application to joining.
          </p>
        </div>
        <span className="result-count">
          {summary?.open_openings ?? 0} open · {summary?.total_applications ?? 0}{' '}
          applications
        </span>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="placement-summary">
        <div>
          <span>Companies</span>
          <strong>{summary?.companies ?? 0}</strong>
          <small>hiring partners</small>
        </div>
        <div>
          <span>Open openings</span>
          <strong>{summary?.open_openings ?? 0}</strong>
          <small>live vacancies</small>
        </div>
        <div>
          <span>Applications</span>
          <strong>{summary?.total_applications ?? 0}</strong>
          <small>in the pipeline</small>
        </div>
        <div>
          <span>Offers released</span>
          <strong>{summary?.offers_released ?? 0}</strong>
          <small>{summary?.joined ?? 0} joined</small>
        </div>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">COMPANY DATABASE</span>
            <h2>Hiring partners</h2>
          </div>
          <span className="result-count">{companies.length} companies</span>
        </div>
        <form className="placement-form-block" onSubmit={(event) => void createCompany(event)}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="placement-company-name">Company</label>
              <input
                id="placement-company-name"
                onChange={(event) =>
                  setCompanyForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="e.g. Infotech Solutions"
                required
                value={companyForm.name}
              />
            </div>
            <div className="field">
              <label htmlFor="placement-company-industry">Industry</label>
              <input
                id="placement-company-industry"
                onChange={(event) =>
                  setCompanyForm((current) => ({ ...current, industry: event.target.value }))
                }
                placeholder="e.g. Software"
                value={companyForm.industry}
              />
            </div>
            <div className="field">
              <label htmlFor="placement-company-location">Location</label>
              <input
                id="placement-company-location"
                onChange={(event) =>
                  setCompanyForm((current) => ({ ...current, location: event.target.value }))
                }
                placeholder="City"
                value={companyForm.location}
              />
            </div>
            <div className="field">
              <label htmlFor="placement-company-contact">Contact person</label>
              <input
                id="placement-company-contact"
                onChange={(event) =>
                  setCompanyForm((current) => ({
                    ...current,
                    contact_person: event.target.value,
                  }))
                }
                placeholder="HR name"
                value={companyForm.contact_person}
              />
            </div>
            <div className="field">
              <label htmlFor="placement-company-email">Contact email</label>
              <input
                id="placement-company-email"
                onChange={(event) =>
                  setCompanyForm((current) => ({
                    ...current,
                    contact_email: event.target.value,
                  }))
                }
                placeholder="hr@company.com"
                type="email"
                value={companyForm.contact_email}
              />
            </div>
            <div className="field">
              <label htmlFor="placement-company-phone">Contact phone</label>
              <input
                id="placement-company-phone"
                onChange={(event) =>
                  setCompanyForm((current) => ({
                    ...current,
                    contact_phone: event.target.value,
                  }))
                }
                placeholder="+91 …"
                value={companyForm.contact_phone}
              />
            </div>
          </div>
          <div className="placement-form-actions">
            <button className="primary-button" disabled={busy === 'company'} type="submit">
              {busy === 'company' ? 'Saving…' : 'Add company'}
            </button>
          </div>
        </form>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Industry</th>
                <th>Location</th>
                <th>Contact</th>
                <th>Openings</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {companies.map((company) => (
                <tr key={company.id}>
                  <td>
                    <strong>{company.name}</strong>
                    {company.website && (
                      <small className="muted-block">{company.website}</small>
                    )}
                  </td>
                  <td>{company.industry ?? '—'}</td>
                  <td>{company.location ?? '—'}</td>
                  <td>
                    {company.contact_person ?? '—'}
                    <small className="muted-block">
                      {company.contact_email ?? company.contact_phone ?? ''}
                    </small>
                  </td>
                  <td>{company.openings_count}</td>
                  <td>
                    <span
                      className={`status-pill ${
                        company.is_active ? 'active-status' : 'inactive-status'
                      }`}
                    >
                      <i />
                      {company.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        disabled={busy === `company-${company.id}`}
                        onClick={() => void toggleCompany(company)}
                        type="button"
                      >
                        {company.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        className="danger-action"
                        disabled={busy === `company-${company.id}`}
                        onClick={() => void deleteCompany(company)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!companies.length && !loading && (
            <div className="table-state">
              <strong>No companies yet</strong>
              <p>Add the first hiring partner above.</p>
            </div>
          )}
        </div>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">JOB OPENINGS</span>
            <h2>Live vacancies</h2>
          </div>
          <span className="result-count">{openings.length} openings</span>
        </div>
        <form className="placement-form-block" onSubmit={(event) => void createOpening(event)}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="opening-company">Company</label>
              <select
                id="opening-company"
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    company_id: event.target.value,
                  }))
                }
                required
                value={openingForm.company_id}
              >
                <option value="">Select a company</option>
                {activeCompanies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="opening-title">Role title</label>
              <input
                id="opening-title"
                onChange={(event) =>
                  setOpeningForm((current) => ({ ...current, title: event.target.value }))
                }
                placeholder="e.g. Junior Python Developer"
                required
                value={openingForm.title}
              />
            </div>
            <div className="field">
              <label htmlFor="opening-location">Location</label>
              <input
                id="opening-location"
                onChange={(event) =>
                  setOpeningForm((current) => ({ ...current, location: event.target.value }))
                }
                placeholder="City or Remote"
                value={openingForm.location}
              />
            </div>
            <div className="field">
              <label htmlFor="opening-type">Employment type</label>
              <select
                id="opening-type"
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    employment_type: event.target.value,
                  }))
                }
                value={openingForm.employment_type}
              >
                {EMPLOYMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="opening-mode">Work mode</label>
              <select
                id="opening-mode"
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    work_mode: event.target.value,
                  }))
                }
                value={openingForm.work_mode}
              >
                {WORK_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {mode}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="opening-vacancies">Vacancies</label>
              <input
                id="opening-vacancies"
                min={1}
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    vacancies: event.target.value,
                  }))
                }
                type="number"
                value={openingForm.vacancies}
              />
            </div>
            <div className="field">
              <label htmlFor="opening-salary-min">Salary min (₹)</label>
              <input
                id="opening-salary-min"
                min={0}
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    salary_min: event.target.value,
                  }))
                }
                placeholder="18000"
                type="number"
                value={openingForm.salary_min}
              />
            </div>
            <div className="field">
              <label htmlFor="opening-salary-max">Salary max (₹)</label>
              <input
                id="opening-salary-max"
                min={0}
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    salary_max: event.target.value,
                  }))
                }
                placeholder="25000"
                type="number"
                value={openingForm.salary_max}
              />
            </div>
            <div className="field">
              <label htmlFor="opening-last-date">Last date</label>
              <input
                id="opening-last-date"
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    last_date: event.target.value,
                  }))
                }
                type="date"
                value={openingForm.last_date}
              />
            </div>
            <div className="field full-field">
              <label htmlFor="opening-description">Description</label>
              <textarea
                id="opening-description"
                onChange={(event) =>
                  setOpeningForm((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
                placeholder="Responsibilities, skills and interview process"
                rows={3}
                value={openingForm.description}
              />
            </div>
          </div>
          <div className="placement-course-picker">
            <span>Eligible courses</span>
            <div className="placement-course-options">
              {courses.map((course) => (
                <label className="checkbox-label" key={course.id}>
                  <input
                    checked={openingCourseIds.includes(course.id)}
                    onChange={() => toggleCourse(course.id)}
                    type="checkbox"
                  />
                  {course.name}
                </label>
              ))}
            </div>
            <small className="muted">
              Leave every course unchecked to open the vacancy to all courses.
            </small>
          </div>
          <div className="placement-form-actions">
            <button className="primary-button" disabled={busy === 'opening'} type="submit">
              {busy === 'opening' ? 'Publishing…' : 'Publish opening'}
            </button>
          </div>
        </form>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Role</th>
                <th>Company</th>
                <th>Eligibility</th>
                <th>Salary</th>
                <th>Last date</th>
                <th>Applicants</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {openings.map((opening) => (
                <tr key={opening.id}>
                  <td>
                    <strong>{opening.title}</strong>
                    <small className="muted-block">
                      {opening.employment_type} · {opening.work_mode}
                      {opening.branch_name ? ` · ${opening.branch_name}` : ' · All branches'}
                    </small>
                  </td>
                  <td>{opening.company_name}</td>
                  <td>
                    {opening.course_names.length
                      ? opening.course_names.join(', ')
                      : 'All courses'}
                  </td>
                  <td>{formatSalary(opening.salary_min, opening.salary_max)}</td>
                  <td>{opening.last_date ?? 'Open'}</td>
                  <td>{opening.applications_count}</td>
                  <td>
                    <span
                      className={`status-pill ${
                        opening.status === 'open' ? 'active-status' : 'inactive-status'
                      }`}
                    >
                      <i />
                      {opening.status}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        disabled={busy === `opening-${opening.id}`}
                        onClick={() => void toggleOpening(opening)}
                        type="button"
                      >
                        {opening.status === 'open' ? 'Close' : 'Reopen'}
                      </button>
                      <button
                        className="danger-action"
                        disabled={busy === `opening-${opening.id}`}
                        onClick={() => void deleteOpening(opening)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!openings.length && !loading && (
            <div className="table-state">
              <strong>No job openings yet</strong>
              <p>Publish a vacancy and eligible students will see it in their portal.</p>
            </div>
          )}
        </div>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">PIPELINE</span>
            <h2>Applications and offers</h2>
          </div>
          <div className="section-actions">
            <input
              className="placement-search"
              onChange={(event) => setApplicationSearch(event.target.value)}
              placeholder="Search student, company or role"
              value={applicationSearch}
            />
            <select
              onChange={(event) => setStatusFilter(event.target.value)}
              value={statusFilter}
            >
              <option value="all">All statuses</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {statusLabel(status)}
                </option>
              ))}
            </select>
            <button
              className="primary-button"
              disabled={!openings.length || !students.length}
              onClick={() => setShowAddApplication(true)}
              type="button"
            >
              Add application
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Opening</th>
                <th>Course</th>
                <th>Applied</th>
                <th>Status</th>
                <th>Interview</th>
                <th>Offer</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filteredApplications.map((application) => (
                <tr key={application.id}>
                  <td>
                    <strong>{application.student_name}</strong>
                    <small className="muted-block">
                      {application.student_code} · {application.branch_name}
                    </small>
                  </td>
                  <td>
                    {application.opening_title}
                    <small className="muted-block">{application.company_name}</small>
                  </td>
                  <td>{application.course_names.join(', ') || '—'}</td>
                  <td>{application.applied_at.slice(0, 10)}</td>
                  <td>
                    <select
                      disabled={busy === `application-${application.id}`}
                      onChange={(event) =>
                        void quickStatus(application, event.target.value)
                      }
                      value={application.status}
                    >
                      {STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {statusLabel(status)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    {formatDateTime(application.interview_date)}
                    {application.interview_mode && (
                      <small className="muted-block">{application.interview_mode}</small>
                    )}
                  </td>
                  <td>
                    {application.offer_salary
                      ? `₹${Number(application.offer_salary).toLocaleString('en-IN')}`
                      : '—'}
                    {application.joining_date && (
                      <small className="muted-block">
                        Joins {application.joining_date}
                      </small>
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button onClick={() => openEditor(application)} type="button">
                        Details
                      </button>
                      <button
                        className="danger-action"
                        disabled={busy === `application-${application.id}`}
                        onClick={() => void deleteApplication(application)}
                        type="button"
                      >
                        Remove
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filteredApplications.length && (
            <div className="table-state">
              {loading
                ? 'Loading applications…'
                : 'No applications match the current filters.'}
            </div>
          )}
        </div>
      </section>

      {showAddApplication && (
        <div className="modal-backdrop" onClick={() => setShowAddApplication(false)}>
          <form
            className="modal-card"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void addApplication(event)}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">ADD TO PIPELINE</span>
                <h2>Student application</h2>
              </div>
              <button
                className="close-button"
                onClick={() => setShowAddApplication(false)}
                type="button"
              >
                ×
              </button>
            </div>
            <div className="form-grid">
              <div className="field full-field">
                <label htmlFor="application-opening">Job opening</label>
                <select
                  id="application-opening"
                  onChange={(event) =>
                    setAddForm((current) => ({
                      ...current,
                      job_opening_id: event.target.value,
                    }))
                  }
                  required
                  value={addForm.job_opening_id}
                >
                  <option value="">Select an opening</option>
                  {openings.map((opening) => (
                    <option key={opening.id} value={opening.id}>
                      {opening.title} · {opening.company_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field full-field">
                <label htmlFor="application-student">Student</label>
                <select
                  id="application-student"
                  onChange={(event) =>
                    setAddForm((current) => ({
                      ...current,
                      student_id: event.target.value,
                    }))
                  }
                  required
                  value={addForm.student_id}
                >
                  <option value="">Select a student</option>
                  {students.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.full_name} ({student.student_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="field full-field">
                <label htmlFor="application-resume">Resume URL</label>
                <input
                  id="application-resume"
                  onChange={(event) =>
                    setAddForm((current) => ({
                      ...current,
                      resume_url: event.target.value,
                    }))
                  }
                  placeholder="https://drive.google.com/…"
                  value={addForm.resume_url}
                />
              </div>
              <div className="field full-field">
                <label htmlFor="application-note">Cover note</label>
                <textarea
                  id="application-note"
                  onChange={(event) =>
                    setAddForm((current) => ({
                      ...current,
                      cover_note: event.target.value,
                    }))
                  }
                  rows={3}
                  value={addForm.cover_note}
                />
              </div>
            </div>
            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => setShowAddApplication(false)}
                type="button"
              >
                Cancel
              </button>
              <button className="primary-button" disabled={busy === 'application'} type="submit">
                {busy === 'application' ? 'Saving…' : 'Add application'}
              </button>
            </div>
          </form>
        </div>
      )}

      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <form
            className="modal-card placement-edit-card"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void saveApplication(event)}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">PLACEMENT RECORD</span>
                <h2>
                  {editing.student_name} · {editing.opening_title}
                </h2>
                <p>{editing.company_name}</p>
              </div>
              <button className="close-button" onClick={() => setEditing(null)} type="button">
                ×
              </button>
            </div>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="edit-status">Status</label>
                <select
                  id="edit-status"
                  onChange={(event) =>
                    setEditForm((current) => ({ ...current, status: event.target.value }))
                  }
                  value={editForm.status}
                >
                  {STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {statusLabel(status)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="edit-interview-date">Interview date</label>
                <input
                  id="edit-interview-date"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      interview_date: event.target.value,
                    }))
                  }
                  type="datetime-local"
                  value={editForm.interview_date}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-interview-mode">Interview mode</label>
                <select
                  id="edit-interview-mode"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      interview_mode: event.target.value,
                    }))
                  }
                  value={editForm.interview_mode}
                >
                  <option value="">Not scheduled</option>
                  {INTERVIEW_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {mode}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="edit-interview-location">Interview venue / link</label>
                <input
                  id="edit-interview-location"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      interview_location: event.target.value,
                    }))
                  }
                  value={editForm.interview_location}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-offer-salary">Offer salary (₹)</label>
                <input
                  id="edit-offer-salary"
                  min={0}
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      offer_salary: event.target.value,
                    }))
                  }
                  type="number"
                  value={editForm.offer_salary}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-offer-date">Offer date</label>
                <input
                  id="edit-offer-date"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      offer_date: event.target.value,
                    }))
                  }
                  type="date"
                  value={editForm.offer_date}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-joining-date">Joining date</label>
                <input
                  id="edit-joining-date"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      joining_date: event.target.value,
                    }))
                  }
                  type="date"
                  value={editForm.joining_date}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-offer-letter">Offer letter URL</label>
                <input
                  id="edit-offer-letter"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      offer_letter_url: event.target.value,
                    }))
                  }
                  placeholder="https://…/offer.pdf"
                  value={editForm.offer_letter_url}
                />
              </div>
              <div className="field full-field">
                <label htmlFor="edit-feedback">Interview feedback</label>
                <textarea
                  id="edit-feedback"
                  onChange={(event) =>
                    setEditForm((current) => ({
                      ...current,
                      feedback: event.target.value,
                    }))
                  }
                  rows={3}
                  value={editForm.feedback}
                />
              </div>
            </div>
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button
                className="primary-button"
                disabled={busy === `application-${editing.id}`}
                type="submit"
              >
                {busy === `application-${editing.id}` ? 'Saving…' : 'Save record'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

export default PlacementPage
