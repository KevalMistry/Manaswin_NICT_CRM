import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'

type Course = {
  id: number
  name: string
  code: string
  description: string | null
  duration_months: number
  fee_amount: number | string | null
  registration_fee: number | string
  application_fee: number | string
  exam_fee: number | string
  is_active: boolean
}

type Branch = { id: number; name: string; code: string; is_active: boolean }
type Faculty = { id: number; full_name: string; branch_id: number | null; is_active: boolean; role_name?: string }
type Batch = {
  id: number
  name: string
  code: string
  course_id: number
  branch_id: number
  faculty_id: number | null
  start_date: string
  end_date: string | null
  capacity: number
  is_active: boolean
}

type CourseForm = { name: string; code: string; description: string; duration_months: string; fee_amount: string; registration_fee: string; application_fee: string; exam_fee: string }
type BatchForm = {
  name: string
  code: string
  course_id: string
  branch_id: string
  start_date: string
  end_date: string
  capacity: string
  faculty_id: string
}

const emptyCourse: CourseForm = { name: '', code: '', description: '', duration_months: '6', fee_amount: '', registration_fee: '0', application_fee: '0', exam_fee: '0' }
const emptyBatch: BatchForm = { name: '', code: '', course_id: '', branch_id: '', start_date: '', end_date: '', capacity: '30', faculty_id: '' }

function CoursesPage() {
  const [tab, setTab] = useState<'courses' | 'batches'>('courses')
  const [courses, setCourses] = useState<Course[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [faculty, setFaculty] = useState<Faculty[]>([])
  const [courseForm, setCourseForm] = useState<CourseForm>(emptyCourse)
  const [batchForm, setBatchForm] = useState<BatchForm>(emptyBatch)
  const [editingCourseId, setEditingCourseId] = useState<number | null>(null)
  const [editingBatchId, setEditingBatchId] = useState<number | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const currentUser = JSON.parse(localStorage.getItem('current_user') ?? '{}') as { role_name?: string }
  const roleName = currentUser.role_name ?? ''
  const canManagePrograms = ['Super Admin', 'Branch Admin', 'Staff'].includes(roleName)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const shouldLoadFaculty =
        canManagePrograms || roleName === 'Faculty'
      const [courseResponse, batchResponse, branchResponse, facultyResponse] = await Promise.all([
        api.get<Course[]>('/api/courses', { params: { include_inactive: true } }),
        api.get<Batch[]>('/api/batches', { params: { include_inactive: true } }),
        api.get<Branch[]>('/api/branches'),
        shouldLoadFaculty
          ? api.get<Faculty[]>('/api/staff/faculty')
          : Promise.resolve({ data: [] as Faculty[] }),
      ])
      setCourses(courseResponse.data)
      setBatches(batchResponse.data)
      setBranches(branchResponse.data)
      setFaculty(facultyResponse.data.filter((user) => user.is_active && user.role_name === 'Faculty'))
    } catch {
      setError('Could not load courses and batches. Check that the API is running and your account has access.')
    } finally {
      setIsLoading(false)
    }
  }, [canManagePrograms, roleName])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  function openCourseForm(course?: Course) {
    setEditingCourseId(course?.id ?? null)
    setEditingBatchId(null)
    setCourseForm(course ? {
      name: course.name,
      code: course.code,
      description: course.description ?? '',
      duration_months: String(course.duration_months),
      fee_amount: course.fee_amount !== null ? String(course.fee_amount) : '',
      registration_fee: String(course.registration_fee ?? 0),
      application_fee: String(course.application_fee ?? 0),
      exam_fee: String(course.exam_fee ?? 0),
    } : emptyCourse)
    setError('')
    setIsFormOpen(true)
  }

  function openBatchForm(batch?: Batch) {
    setEditingBatchId(batch?.id ?? null)
    setEditingCourseId(null)
    setBatchForm(batch ? {
      name: batch.name,
      code: batch.code,
      course_id: String(batch.course_id),
      branch_id: String(batch.branch_id),
      start_date: batch.start_date,
      end_date: batch.end_date ?? '',
      capacity: String(batch.capacity),
      faculty_id: batch.faculty_id ? String(batch.faculty_id) : '',
    } : { ...emptyBatch, course_id: courses[0] ? String(courses[0].id) : '', branch_id: branches[0] ? String(branches[0].id) : '' })
    setError('')
    setIsFormOpen(true)
  }

  async function submitCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    const payload = { ...courseForm, duration_months: Number(courseForm.duration_months), description: courseForm.description || null, fee_amount: courseForm.fee_amount ? Number(courseForm.fee_amount) : null, registration_fee: courseForm.registration_fee ? Number(courseForm.registration_fee) : 0, application_fee: courseForm.application_fee ? Number(courseForm.application_fee) : 0, exam_fee: courseForm.exam_fee ? Number(courseForm.exam_fee) : 0 }
    try {
      if (editingCourseId) await api.patch(`/api/courses/${editingCourseId}`, payload)
      else await api.post('/api/courses', payload)
      setIsFormOpen(false)
      await loadData()
    } catch {
      setError('Unable to save this course. Check the course code and required fields.')
    } finally {
      setIsSaving(false)
    }
  }

  async function submitBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    const payload = {
      name: batchForm.name,
      code: batchForm.code,
      course_id: Number(batchForm.course_id),
      branch_id: Number(batchForm.branch_id),
      start_date: batchForm.start_date,
      end_date: batchForm.end_date || null,
      capacity: Number(batchForm.capacity),
      faculty_id: batchForm.faculty_id ? Number(batchForm.faculty_id) : null,
    }
    try {
      if (editingBatchId) await api.patch(`/api/batches/${editingBatchId}`, payload)
      else await api.post('/api/batches', payload)
      setIsFormOpen(false)
      await loadData()
    } catch {
      setError('Unable to save this batch. Check the dates, code, and selected references.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deactivate(type: 'course' | 'batch', id: number, name: string) {
    if (!window.confirm(`Deactivate ${name}?`)) return
    try {
      await api.delete(`/api/${type === 'course' ? 'courses' : 'batches'}/${id}`)
      await loadData()
    } catch {
      setError(`Unable to deactivate this ${type}.`)
    }
  }

  async function reactivate(type: 'course' | 'batch', id: number) {
    try {
      await api.patch(`/api/${type === 'course' ? 'courses' : 'batches'}/${id}`, { is_active: true })
      await loadData()
    } catch {
      setError(`Unable to reactivate this ${type}.`)
    }
  }

  const filteredCourses = courses.filter((course) => `${course.name} ${course.code}`.toLowerCase().includes(search.toLowerCase()))
  const filteredBatches = batches.filter((batch) => `${batch.name} ${batch.code}`.toLowerCase().includes(search.toLowerCase()))
  const courseName = (id: number) => courses.find((course) => course.id === id)?.name ?? `Course #${id}`
  const branchName = (id: number) => branches.find((branch) => branch.id === id)?.name ?? `Branch #${id}`

  return (
    <>
      <div className="page-heading module-heading">
        <div><span className="eyebrow">PROGRAMS</span><h1>Courses &amp; batches</h1><p>Define your programs and organize student learning groups.</p></div>
        {canManagePrograms && <button className="primary-button" onClick={() => tab === 'courses' ? openCourseForm() : openBatchForm()} type="button">+ Add {tab === 'courses' ? 'course' : 'batch'}</button>}
      </div>
      {error && <div className="inline-error">{error}</div>}
      <section className="module-tabs"><button className={tab === 'courses' ? 'active-tab' : ''} onClick={() => { setTab('courses'); setSearch('') }} type="button">Courses <span>{courses.length}</span></button><button className={tab === 'batches' ? 'active-tab' : ''} onClick={() => { setTab('batches'); setSearch('') }} type="button">Batches <span>{batches.length}</span></button></section>
      <section className="module-toolbar"><div className="search-box"><span>⌕</span><input aria-label={`Search ${tab}`} placeholder={`Search ${tab}…`} value={search} onChange={(event) => setSearch(event.target.value)} /></div><span className="result-count">{tab === 'courses' ? filteredCourses.length : filteredBatches.length} results</span></section>
      <section className="data-panel">
        {isLoading ? <div className="table-state">Loading {tab}…</div> : tab === 'courses' ? (
          filteredCourses.length === 0 ? <div className="table-state"><div className="empty-icon">▦</div><strong>No courses found</strong><p>Create a course to start building your programs.</p></div> :
          <div className="table-wrap"><table><thead><tr><th>Course</th><th>Code</th><th>Duration</th><th>Course fee</th><th>Application</th><th>Exam</th><th>Registration</th><th>Batches</th><th>Status</th><th /></tr></thead><tbody>{filteredCourses.map((course) => <tr key={course.id}><td><div className="branch-name"><span className="branch-avatar">{course.name.slice(0, 1).toUpperCase()}</span><span><strong>{course.name}</strong><small>{course.description || 'No description added'}</small></span></div></td><td><span className="code-pill">{course.code}</span></td><td>{course.duration_months} months</td><td>{course.fee_amount !== null && Number(course.fee_amount) > 0 ? `₹${Number(course.fee_amount).toLocaleString('en-IN')}` : <span className="fee-not-set">Not set</span>}</td><td>{Number(course.application_fee) > 0 ? `₹${Number(course.application_fee).toLocaleString('en-IN')}` : <span className="fee-not-set">Free</span>}</td><td>{Number(course.exam_fee) > 0 ? `₹${Number(course.exam_fee).toLocaleString('en-IN')}` : <span className="fee-not-set">Free</span>}</td><td>{Number(course.registration_fee) > 0 ? `₹${Number(course.registration_fee).toLocaleString('en-IN')}` : <span className="fee-not-set">Free</span>}</td><td>{batches.filter((batch) => batch.course_id === course.id).length}</td><td><span className={course.is_active ? 'status-pill active-status' : 'status-pill inactive-status'}><i />{course.is_active ? 'Active' : 'Inactive'}</span></td><td>{canManagePrograms && <div className="row-actions"><button onClick={() => openCourseForm(course)} type="button">Edit</button>{course.is_active ? <button className="danger-action" onClick={() => void deactivate('course', course.id, course.name)} type="button">Deactivate</button> : <button onClick={() => void reactivate('course', course.id)} type="button">Reactivate</button>}</div>}</td></tr>)}</tbody></table></div>
        ) : filteredBatches.length === 0 ? <div className="table-state"><div className="empty-icon">▤</div><strong>No batches found</strong><p>Create a batch after adding a course and branch.</p></div> :
          <div className="table-wrap"><table><thead><tr><th>Batch</th><th>Course</th><th>Branch</th><th>Dates</th><th>Capacity</th><th>Status</th><th /></tr></thead><tbody>{filteredBatches.map((batch) => <tr key={batch.id}><td><div className="branch-name"><span className="branch-avatar">{batch.name.slice(0, 1).toUpperCase()}</span><span><strong>{batch.name}</strong><small>{batch.code}</small></span></div></td><td>{courseName(batch.course_id)}</td><td>{branchName(batch.branch_id)}</td><td>{batch.start_date}{batch.end_date ? ` – ${batch.end_date}` : ''}</td><td>{batch.capacity}</td><td><span className={batch.is_active ? 'status-pill active-status' : 'status-pill inactive-status'}><i />{batch.is_active ? 'Active' : 'Inactive'}</span></td><td>{canManagePrograms && <div className="row-actions"><button onClick={() => openBatchForm(batch)} type="button">Edit</button>{batch.is_active ? <button className="danger-action" onClick={() => void deactivate('batch', batch.id, batch.name)} type="button">Deactivate</button> : <button onClick={() => void reactivate('batch', batch.id)} type="button">Reactivate</button>}</div>}</td></tr>)}</tbody></table></div>}
      </section>
      {isFormOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsFormOpen(false) }}><div className="modal-card" role="dialog" aria-modal="true">
        <div className="modal-header"><div><span className="eyebrow">{editingCourseId || !editingBatchId ? 'COURSE' : 'BATCH'}</span><h2>{editingCourseId ? 'Update course' : editingBatchId ? 'Update batch' : tab === 'courses' ? 'Add a course' : 'Add a batch'}</h2></div><button className="close-button" onClick={() => setIsFormOpen(false)} type="button">×</button></div>
        {tab === 'courses' || editingCourseId ? <form onSubmit={submitCourse}><div className="form-grid"><div className="field"><label htmlFor="course-name">Course name</label><input id="course-name" value={courseForm.name} onChange={(event) => setCourseForm({ ...courseForm, name: event.target.value })} required /></div><div className="field"><label htmlFor="course-code">Course code</label><input id="course-code" value={courseForm.code} onChange={(event) => setCourseForm({ ...courseForm, code: event.target.value.toUpperCase() })} required /></div><div className="field"><label htmlFor="course-duration">Duration (months)</label><input id="course-duration" type="number" min="1" max="120" value={courseForm.duration_months} onChange={(event) => setCourseForm({ ...courseForm, duration_months: event.target.value })} required /></div><div className="field"><label htmlFor="course-fee">Course fee (₹)</label><input id="course-fee" type="number" min="0" step="0.01" value={courseForm.fee_amount} onChange={(event) => setCourseForm({ ...courseForm, fee_amount: event.target.value })} placeholder="e.g. 60000" /><small className="field-hint">Used to pre-fill fee plans for this course.</small></div>        <div className="field"><label htmlFor="course-application-fee">Application fee (₹)</label><input id="course-application-fee" type="number" min="0" step="0.01" value={courseForm.application_fee} onChange={(event) => setCourseForm({ ...courseForm, application_fee: event.target.value })} placeholder="e.g. 500" /></div><div className="field"><label htmlFor="course-exam-fee">Exam fee (₹)</label><input id="course-exam-fee" type="number" min="0" step="0.01" value={courseForm.exam_fee} onChange={(event) => setCourseForm({ ...courseForm, exam_fee: event.target.value })} placeholder="e.g. 1000" /></div><div className="field"><label htmlFor="course-registration-fee">Registration fee (₹)</label><input id="course-registration-fee" type="number" min="0" step="0.01" value={courseForm.registration_fee} onChange={(event) => setCourseForm({ ...courseForm, registration_fee: event.target.value })} placeholder="e.g. 2000" /><small className="field-hint">Collected online or at the branch during admission.</small></div><div className="field full-field"><label htmlFor="course-description">Description</label><textarea id="course-description" value={courseForm.description} onChange={(event) => setCourseForm({ ...courseForm, description: event.target.value })} rows={3} /></div></div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Saving…' : editingCourseId ? 'Save changes' : 'Create course'}</button></div></form> :
          <form onSubmit={submitBatch}><div className="form-grid"><div className="field"><label htmlFor="batch-name">Batch name</label><input id="batch-name" value={batchForm.name} onChange={(event) => setBatchForm({ ...batchForm, name: event.target.value })} required /></div><div className="field"><label htmlFor="batch-code">Batch code</label><input id="batch-code" value={batchForm.code} onChange={(event) => setBatchForm({ ...batchForm, code: event.target.value.toUpperCase() })} required /></div><div className="field"><label htmlFor="batch-course">Course</label><select id="batch-course" value={batchForm.course_id} onChange={(event) => setBatchForm({ ...batchForm, course_id: event.target.value })} required><option value="">Select course</option>{courses.filter((course) => course.is_active).map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></div><div className="field"><label htmlFor="batch-branch">Branch</label><select id="batch-branch" value={batchForm.branch_id} onChange={(event) => setBatchForm({ ...batchForm, branch_id: event.target.value })} required><option value="">Select branch</option>{branches.filter((branch) => branch.is_active !== false).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></div><div className="field"><label htmlFor="batch-faculty">Assigned faculty</label><select id="batch-faculty" value={batchForm.faculty_id} onChange={(event) => setBatchForm({ ...batchForm, faculty_id: event.target.value })}><option value="">No faculty assigned</option>{faculty.filter((user) => user.branch_id === Number(batchForm.branch_id)).map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select></div><div className="field"><label htmlFor="batch-start">Start date</label><input id="batch-start" type="date" value={batchForm.start_date} onChange={(event) => setBatchForm({ ...batchForm, start_date: event.target.value })} required /></div><div className="field"><label htmlFor="batch-end">End date</label><input id="batch-end" type="date" value={batchForm.end_date} onChange={(event) => setBatchForm({ ...batchForm, end_date: event.target.value })} /></div><div className="field"><label htmlFor="batch-capacity">Capacity</label><input id="batch-capacity" type="number" min="1" max="1000" value={batchForm.capacity} onChange={(event) => setBatchForm({ ...batchForm, capacity: event.target.value })} required /></div></div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Saving…' : editingBatchId ? 'Save changes' : 'Create batch'}</button></div></form>}
      </div></div>}
    </>
  )
}

export default CoursesPage
