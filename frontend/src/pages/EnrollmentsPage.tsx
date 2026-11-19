import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser, hasModuleAccess } from '../utils/auth'
import { todayInputValue } from '../utils/date'

type Student = { id: number; full_name: string; student_code: string; branch_id: number; is_active: boolean }
type Batch = { id: number; name: string; code: string; course_id: number; branch_id: number; capacity: number; is_active: boolean }
type Course = { id: number; name: string; is_active: boolean }
type Branch = { id: number; name: string; code: string }
type Enrollment = { id: number; enrollment_code: string; student_id: number; batch_id: number; admission_date: string; status: 'active' | 'completed' | 'cancelled'; course_end_date: string | null; days_remaining: number | null }

function EnrollmentsPage() {
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [students, setStudents] = useState<Student[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [courses, setCourses] = useState<Course[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [studentId, setStudentId] = useState('')
  const [batchId, setBatchId] = useState('')
  const [admissionDate, setAdmissionDate] = useState(todayInputValue())
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  const currentUser = getStoredUser()
  const roleName = currentUser?.role_name ?? ''
  const canManageEnrollments =
    hasModuleAccess(currentUser, 'enrollments') &&
    ['Super Admin', 'Branch Admin', 'Staff', 'Counsellor'].includes(roleName)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      // Include inactive records so completed history keeps showing real names
      // instead of "Student #id" / "Batch #id" after a record is deactivated.
      const [enrollmentResponse, studentResponse, batchResponse, courseResponse, branchResponse] =
        await Promise.all([
          api.get<Enrollment[]>('/api/enrollments', { params: { include_cancelled: true } }),
          api.get<Student[]>('/api/students', { params: { include_inactive: true, limit: 100 } }),
          api.get<Batch[]>('/api/batches', { params: { include_inactive: true, limit: 100 } }),
          api.get<Course[]>('/api/courses', { params: { include_inactive: true, limit: 100 } }),
          api.get<Branch[]>('/api/branches'),
        ])
      setEnrollments(enrollmentResponse.data)
      setStudents(studentResponse.data)
      setBatches(batchResponse.data)
      setCourses(courseResponse.data)
      setBranches(branchResponse.data)
    } catch (requestError) {
      setError(
        apiErrorMessage(
          requestError,
          'Could not load enrollment data. Check your account access and API connection.',
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  async function createEnrollment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    try {
      await api.post('/api/enrollments', {
        student_id: Number(studentId),
        batch_id: Number(batchId),
        admission_date: admissionDate,
      })
      setIsFormOpen(false)
      setStudentId('')
      setBatchId('')
      await loadData()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to create the enrollment.'))
    } finally {
      setIsSaving(false)
    }
  }

  async function updateStatus(enrollment: Enrollment, status: 'completed' | 'cancelled') {
    if (!window.confirm(`Mark ${studentName(enrollment.student_id)} as ${status}?`)) return
    setError('')
    try {
      await api.patch(`/api/enrollments/${enrollment.id}`, { status })
      await loadData()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to update enrollment status.'))
    }
  }

  const student = (id: number) => students.find((item) => item.id === id)
  const studentName = (id: number) => student(id)?.full_name ?? `Student #${id}`
  const studentCode = (id: number) => student(id)?.student_code ?? '—'
  const batchOf = (id: number) => batches.find((batch) => batch.id === id)
  const batchName = (id: number) => batchOf(id)?.name ?? `Batch #${id}`
  const branchName = (id: number) => branches.find((branch) => branch.id === id)?.name ?? `Branch #${id}`
  const courseName = (id: number) => {
    const batch = batchOf(id)
    return courses.find((course) => course.id === batch?.course_id)?.name ?? 'Course'
  }

  const selectedStudent = student(Number(studentId))
  const selectedBatch = batchOf(Number(batchId))
  // Keep the batch list on the selected student's branch so a cross-branch
  // admission cannot be submitted by mistake.
  const selectableBatches = useMemo(
    () =>
      batches.filter(
        (batch) => batch.is_active && (!selectedStudent || batch.branch_id === selectedStudent.branch_id),
      ),
    [batches, selectedStudent],
  )
  const activeCountByBatch = useMemo(() => {
    const counts: Record<number, number> = {}
    for (const enrollment of enrollments) {
      if (enrollment.status === 'active') {
        counts[enrollment.batch_id] = (counts[enrollment.batch_id] ?? 0) + 1
      }
    }
    return counts
  }, [enrollments])
  const seatsLeft = selectedBatch
    ? Math.max(0, selectedBatch.capacity - (activeCountByBatch[selectedBatch.id] ?? 0))
    : null

  const filtered = enrollments.filter((item) => {
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter
    const text = `${studentName(item.student_id)} ${studentCode(item.student_id)} ${batchName(item.batch_id)} ${item.enrollment_code}`.toLowerCase()
    return matchesStatus && text.includes(search.toLowerCase())
  })

  function selectStudent(value: string) {
    setStudentId(value)
    const nextStudent = student(Number(value))
    const currentBatch = batchOf(Number(batchId))
    if (nextStudent && currentBatch && nextStudent.branch_id !== currentBatch.branch_id) {
      setBatchId('')
    }
  }

  return (
    <>
      <div className="page-heading module-heading">
        <div><span className="eyebrow">ADMISSIONS</span><h1>Enrollments</h1><p>Place students into batches and track their admission status.</p></div>
        {canManageEnrollments && <button className="primary-button" onClick={() => setIsFormOpen(true)} type="button">+ Create enrollment</button>}
      </div>
      {error && <div className="inline-error">{error}</div>}
      <section className="module-toolbar">
        <div className="search-box"><span>⌕</span><input aria-label="Search enrollments" placeholder="Search students or enrollment IDs…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <div className="toolbar-controls"><select aria-label="Filter enrollment status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="active">Active</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select><span className="result-count">{filtered.length} enrollments</span></div>
      </section>
      <section className="data-panel">
        {isLoading ? <div className="table-state">Loading enrollments…</div> : filtered.length === 0 ? <div className="table-state"><div className="empty-icon">↗</div><strong>{search || statusFilter !== 'all' ? 'No matching enrollments' : 'No enrollments yet'}</strong><p>{search || statusFilter !== 'all' ? 'Try another filter.' : canManageEnrollments ? 'Create an enrollment after adding students and batches.' : 'No enrollment records are available for your access.'}</p>{!search && statusFilter === 'all' && canManageEnrollments && <button className="primary-button" onClick={() => setIsFormOpen(true)} type="button">Create first enrollment</button>}</div> : (
          <div className="table-wrap"><table><thead><tr><th>Student</th><th>Batch</th><th>Course</th><th>Admission date</th><th>Course ends</th><th>Enrollment ID</th><th>Status</th><th /></tr></thead><tbody>{filtered.map((enrollment) => <tr key={enrollment.id}><td><div className="branch-name"><span className="branch-avatar">{studentName(enrollment.student_id).slice(0, 1).toUpperCase()}</span><span><strong>{studentName(enrollment.student_id)}</strong><small>{studentCode(enrollment.student_id)}</small></span></div></td><td>{batchName(enrollment.batch_id)}<small className="muted-block">{branchName(batchOf(enrollment.batch_id)?.branch_id ?? 0)}</small></td><td>{courseName(enrollment.batch_id)}</td><td>{enrollment.admission_date}</td><td>{enrollment.course_end_date ? <span>{enrollment.course_end_date}<small className="muted-block">{enrollment.status === 'completed' ? 'Course finished' : enrollment.days_remaining !== null && enrollment.days_remaining <= 0 ? 'End date reached' : `${enrollment.days_remaining} days left`}</small></span> : '—'}</td><td><span className="code-pill">{enrollment.enrollment_code}</span></td><td><span className={`status-pill ${enrollment.status === 'active' ? 'active-status' : 'inactive-status'}`}><i />{enrollment.status}</span></td><td>{canManageEnrollments && enrollment.status === 'active' && <div className="row-actions"><button onClick={() => void updateStatus(enrollment, 'completed')} type="button">Complete</button><button className="danger-action" onClick={() => void updateStatus(enrollment, 'cancelled')} type="button">Cancel</button></div>}</td></tr>)}</tbody></table></div>
        )}
      </section>
      {isFormOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsFormOpen(false) }}><div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="enrollment-modal-title">
        <div className="modal-header"><div><span className="eyebrow">NEW ADMISSION</span><h2 id="enrollment-modal-title">Create enrollment</h2></div><button className="close-button" onClick={() => setIsFormOpen(false)} type="button">×</button></div>
        <form onSubmit={createEnrollment}><div className="form-grid"><div className="field full-field"><label htmlFor="enrollment-student">Student</label><select id="enrollment-student" value={studentId} onChange={(event) => selectStudent(event.target.value)} required><option value="">Select active student</option>{students.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.full_name} ({item.student_code}) · {branchName(item.branch_id)}</option>)}</select></div><div className="field full-field"><label htmlFor="enrollment-batch">Batch</label><select id="enrollment-batch" value={batchId} onChange={(event) => setBatchId(event.target.value)} required><option value="">{selectedStudent ? `Select active batch in ${branchName(selectedStudent.branch_id)}` : 'Select active batch'}</option>{selectableBatches.map((batch) => <option key={batch.id} value={batch.id}>{batch.name} — {courseName(batch.id)} ({batch.code}) · {branchName(batch.branch_id)}</option>)}</select>{selectedBatch && <small className="field-hint">Capacity {selectedBatch.capacity} · {activeCountByBatch[selectedBatch.id] ?? 0} enrolled · {seatsLeft} seats left</small>}{!selectedStudent && <small className="field-hint">Select a student first to see only batches in their branch.</small>}</div><div className="field"><label htmlFor="enrollment-date">Admission date</label><input id="enrollment-date" type="date" value={admissionDate} onChange={(event) => setAdmissionDate(event.target.value)} required /></div></div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Creating…' : 'Create enrollment'}</button></div></form>
      </div></div>}
    </>
  )
}

export default EnrollmentsPage
