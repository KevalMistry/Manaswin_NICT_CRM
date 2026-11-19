import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser, hasModuleAccess } from '../utils/auth'
import AuthImage from '../components/AuthImage'
import StudentDocumentsModal from '../components/StudentDocumentsModal'
import type { StudentSummary } from '../components/StudentDocumentsModal'

type Student = {
  id: number
  student_code: string
  roll_number: string | null
  full_name: string
  branch_id: number
  email: string | null
  phone: string | null
  date_of_birth: string | null
  gender: string | null
  aadhaar_number: string | null
  pan_number: string | null
  parent_name: string | null
  parent_phone: string | null
  address: string | null
  qualification: string | null
  skill_level: string | null
  photo_url: string | null
  is_active: boolean
  user_id: number | null
}

type Branch = { id: number; name: string; code: string }
type StudentForm = {
  full_name: string
  branch_id: string
  email: string
  phone: string
  date_of_birth: string
  gender: string
  aadhaar_number: string
  pan_number: string
  parent_name: string
  parent_phone: string
  address: string
  qualification: string
  skill_level: string
}

const emptyForm: StudentForm = {
  full_name: '', branch_id: '', email: '', phone: '', date_of_birth: '', gender: '',
  aadhaar_number: '', pan_number: '', parent_name: '', parent_phone: '', address: '',
  qualification: '', skill_level: '',
}

function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [form, setForm] = useState<StudentForm>(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [documentsStudent, setDocumentsStudent] = useState<StudentSummary | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [accountStudent, setAccountStudent] = useState<Student | null>(null)
  const [accountEmail, setAccountEmail] = useState('')
  const [accountPassword, setAccountPassword] = useState('')
  const [isCreatingAccount, setIsCreatingAccount] = useState(false)
  const [accountError, setAccountError] = useState('')
  const currentUser = getStoredUser()
  const roleName = currentUser?.role_name ?? ''
  const canManageStudents =
    hasModuleAccess(currentUser, 'students') &&
    ['Super Admin', 'Branch Admin', 'Staff', 'Counsellor'].includes(roleName)
  // Counsellors create and edit enquiries/students but cannot deactivate a
  // student or create a student login account.
  const canDeactivateStudents = ['Super Admin', 'Branch Admin', 'Staff'].includes(roleName)

  const loadStudents = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const { data } = await api.get<Student[]>('/api/students', { params: { include_inactive: true, search: search || undefined } })
      setStudents(data)
    } catch {
      setError('Could not load students. Check that the API is running and your account has access.')
    } finally {
      setIsLoading(false)
    }
  }, [search])

  useEffect(() => {
    void api.get<Branch[]>('/api/branches').then(({ data }) => setBranches(data)).catch(() => setError('Could not load branches.'))
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadStudents(), 250)
    return () => window.clearTimeout(timer)
  }, [loadStudents])

  function openCreate() {
    setEditingId(null)
    setForm({ ...emptyForm, branch_id: branches[0] ? String(branches[0].id) : '' })
    setError('')
    setPhotoFile(null)
    setIsFormOpen(true)
  }

  function openEdit(student: Student) {
    setEditingId(student.id)
    setForm({
      full_name: student.full_name,
      branch_id: String(student.branch_id),
      email: student.email ?? '',
      phone: student.phone ?? '',
      date_of_birth: student.date_of_birth ?? '',
      gender: student.gender ?? '',
      aadhaar_number: student.aadhaar_number ?? '',
      pan_number: student.pan_number ?? '',
      parent_name: student.parent_name ?? '',
      parent_phone: student.parent_phone ?? '',
      address: student.address ?? '',
      qualification: student.qualification ?? '',
      skill_level: student.skill_level ?? '',
    })
    setError('')
    setPhotoFile(null)
    setIsFormOpen(true)
  }

  function updateField(field: keyof StudentForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    const payload = {
      full_name: form.full_name,
      branch_id: Number(form.branch_id),
      email: form.email || null,
      phone: form.phone || null,
      date_of_birth: form.date_of_birth || null,
      gender: form.gender || null,
      aadhaar_number: form.aadhaar_number || null,
      pan_number: form.pan_number || null,
      parent_name: form.parent_name || null,
      parent_phone: form.parent_phone || null,
      address: form.address || null,
      qualification: form.qualification || null,
      skill_level: form.skill_level || null,
    }
    try {
      const { data: savedStudent } = editingId
        ? await api.patch<Student>(`/api/students/${editingId}`, payload)
        : await api.post<Student>('/api/students', payload)
      if (photoFile) {
        const body = new FormData()
        body.append('file', photoFile)
        await api.post(`/api/students/${savedStudent.id}/photo`, body, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
      setIsFormOpen(false)
      await loadStudents()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to save this student. Review the form and try again.'))
    } finally {
      setIsSaving(false)
    }
  }

  async function deactivate(student: Student) {
    if (!window.confirm(`Deactivate ${student.full_name}?`)) return
    try {
      await api.delete(`/api/students/${student.id}`)
      await loadStudents()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to deactivate this student.'))
    }
  }

  function openCreateAccountModal(student: Student) {
    setAccountStudent(student)
    setAccountEmail(student.email ?? '')
    setAccountPassword('')
    setAccountError('')
  }

  async function submitCreateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accountStudent) return
    setIsCreatingAccount(true)
    setAccountError('')
    try {
      await api.post(`/api/students/${accountStudent.id}/account`, {
        email: accountEmail.trim(),
        password: accountPassword,
      })
      setAccountStudent(null)
      await loadStudents()
    } catch (requestError) {
      setAccountError(
        apiErrorMessage(
          requestError,
          'Unable to create the student account. Check that the email is unique and the password has at least 8 characters.',
        ),
      )
    } finally {
      setIsCreatingAccount(false)
    }
  }

  const branchName = (id: number) => branches.find((branch) => branch.id === id)?.name ?? `Branch #${id}`

  return (
    <>
      <div className="page-heading module-heading">
        <div><span className="eyebrow">PEOPLE</span><h1>Students</h1><p>Keep student profiles and contact information organized.</p></div>
        {canManageStudents && <button className="primary-button" onClick={openCreate} type="button">+ Add student</button>}
      </div>
      {error && <div className="inline-error">{error}</div>}
      <section className="module-toolbar">
        <div className="search-box"><span>⌕</span><input aria-label="Search students" placeholder="Search by student name…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <span className="result-count">{students.length} {students.length === 1 ? 'student' : 'students'}</span>
      </section>
      <section className="data-panel">
        {isLoading ? <div className="table-state">Loading students…</div> : students.length === 0 ? (
          <div className="table-state"><div className="empty-icon">♙</div><strong>{search ? 'No matching students' : 'No students yet'}</strong><p>{search ? 'Try a different search term.' : canManageStudents ? 'Add your first student to begin.' : 'No student records are available for your access.'}</p>{!search && canManageStudents && <button className="primary-button" onClick={openCreate} type="button">Add your first student</button>}</div>
        ) : (
          <div className="table-wrap"><table><thead><tr><th>Student</th><th>Student ID</th><th>Branch</th><th>Contact</th><th>Status</th><th /></tr></thead><tbody>
            {students.map((student) => <tr key={student.id}><td><div className="branch-name">{student.photo_url ? <AuthImage className="branch-avatar student-list-photo" path={student.photo_url} alt="" /> : <span className="branch-avatar">{student.full_name.slice(0, 1).toUpperCase()}</span>}<span><strong>{student.full_name}</strong><small>{student.qualification || 'Qualification not added'}</small></span></div></td><td><span className="code-pill">{student.student_code}</span>{student.roll_number && <small className="roll-number">{student.roll_number}</small>}</td><td>{branchName(student.branch_id)}</td><td><span className="contact-cell">{student.email || student.phone || '—'}</span></td><td><span className={student.is_active ? 'status-pill active-status' : 'status-pill inactive-status'}><i />{student.is_active ? 'Active' : 'Inactive'}</span></td><td>{canManageStudents && <div className="row-actions"><button onClick={() => setDocumentsStudent({ id: student.id, full_name: student.full_name, student_code: student.student_code, photo_url: student.photo_url })} type="button">Documents</button><button onClick={() => openEdit(student)} type="button">Edit</button>{canDeactivateStudents && student.is_active && !student.user_id && <button onClick={() => openCreateAccountModal(student)} type="button">Create login</button>}{canDeactivateStudents && student.is_active && <button className="danger-action" onClick={() => void deactivate(student)} type="button">Deactivate</button>}</div>}</td></tr>)}
          </tbody></table></div>
        )}
      </section>
      {isFormOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsFormOpen(false) }}><div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="student-modal-title">
        <div className="modal-header"><div><span className="eyebrow">{editingId ? 'EDIT STUDENT' : 'NEW STUDENT'}</span><h2 id="student-modal-title">{editingId ? 'Update student' : 'Add a student'}</h2></div><button className="close-button" onClick={() => setIsFormOpen(false)} type="button">×</button></div>
        <form onSubmit={submit}><div className="form-grid">
<div className="field full-field"><label htmlFor="student-name">Full name</label><input id="student-name" value={form.full_name} onChange={(event) => updateField('full_name', event.target.value)} placeholder="Student full name" required /></div>
<div className="field full-field"><label htmlFor="student-photo">Student photo</label><input id="student-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setPhotoFile(event.target.files?.[0] ?? null)} /><small className="field-hint">JPG, PNG or WebP, up to 3 MB.</small></div>
<div className="field"><label htmlFor="student-branch">Branch</label><select id="student-branch" value={form.branch_id} onChange={(event) => updateField('branch_id', event.target.value)} required><option value="">Select branch</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} ({branch.code})</option>)}</select></div>
<div className="field"><label htmlFor="student-phone">Phone</label><input id="student-phone" value={form.phone} onChange={(event) => updateField('phone', event.target.value)} placeholder="+91…" /></div>
<div className="field"><label htmlFor="student-email">Email</label><input id="student-email" type="email" value={form.email} onChange={(event) => updateField('email', event.target.value)} placeholder="student@example.com" /></div>
<div className="field"><label htmlFor="student-dob">Date of birth</label><input id="student-dob" type="date" value={form.date_of_birth} onChange={(event) => updateField('date_of_birth', event.target.value)} /></div>
<div className="field"><label htmlFor="student-gender">Gender</label><select id="student-gender" value={form.gender} onChange={(event) => updateField('gender', event.target.value)}><option value="">Select gender</option><option value="Male">Male</option><option value="Female">Female</option><option value="Other">Other</option><option value="Prefer not to say">Prefer not to say</option></select></div>
<div className="field"><label htmlFor="student-aadhaar">Aadhaar number</label><input id="student-aadhaar" value={form.aadhaar_number} onChange={(event) => updateField('aadhaar_number', event.target.value)} placeholder="12-digit Aadhaar" maxLength={20} /></div>
<div className="field"><label htmlFor="student-pan">PAN number</label><input id="student-pan" value={form.pan_number} onChange={(event) => updateField('pan_number', event.target.value)} placeholder="ABCDE1234F" maxLength={20} /></div>
<div className="field"><label htmlFor="student-parent-name">Parent / guardian name</label><input id="student-parent-name" value={form.parent_name} onChange={(event) => updateField('parent_name', event.target.value)} placeholder="Guardian name" /></div>
<div className="field"><label htmlFor="student-parent-phone">Parent / guardian phone</label><input id="student-parent-phone" value={form.parent_phone} onChange={(event) => updateField('parent_phone', event.target.value)} placeholder="+91…" /></div>
<div className="field full-field"><label htmlFor="student-address">Address</label><textarea id="student-address" value={form.address} onChange={(event) => updateField('address', event.target.value)} placeholder="Residential address" rows={2} /></div>
<div className="field"><label htmlFor="student-qualification">Qualification</label><input id="student-qualification" value={form.qualification} onChange={(event) => updateField('qualification', event.target.value)} placeholder="e.g. 12th pass" /></div>
<div className="field"><label htmlFor="student-skill">Skill level</label><select id="student-skill" value={form.skill_level} onChange={(event) => updateField('skill_level', event.target.value)}><option value="">Select level</option><option value="Beginner">Beginner</option><option value="Intermediate">Intermediate</option><option value="Advanced">Advanced</option></select></div>
</div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Saving…' : editingId ? 'Save changes' : 'Create student'}</button></div></form>
      </div></div>}
      {documentsStudent && (
        <StudentDocumentsModal
          student={documentsStudent}
          onClose={() => setDocumentsStudent(null)}
          onStudentUpdated={(photoUrl) => {
            setDocumentsStudent((current) => (current ? { ...current, photo_url: photoUrl } : current))
            void loadStudents()
          }}
        />
      )}
      {accountStudent && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setAccountStudent(null) }}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="create-login-title">
            <div className="modal-header">
              <div>
                <span className="eyebrow">PORTAL ACCESS</span>
                <h2 id="create-login-title">Create student login</h2>
              </div>
              <button className="close-button" onClick={() => setAccountStudent(null)} type="button">×</button>
            </div>
            {accountError && <div className="inline-error">{accountError}</div>}
            <form onSubmit={submitCreateAccount}>
              <div className="form-grid">
                <div className="field full-field">
                  <label htmlFor="account-name">Student</label>
                  <input id="account-name" value={`${accountStudent.full_name} (${accountStudent.student_code})`} disabled />
                </div>
                <div className="field full-field">
                  <label htmlFor="account-email">Login email</label>
                  <input
                    id="account-email"
                    type="email"
                    value={accountEmail}
                    onChange={(e) => setAccountEmail(e.target.value)}
                    placeholder="student@example.com"
                    required
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="account-pwd">Temporary password</label>
                  <input
                    id="account-pwd"
                    type="password"
                    minLength={8}
                    value={accountPassword}
                    onChange={(e) => setAccountPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    required
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setAccountStudent(null)} type="button">Cancel</button>
                <button className="primary-button" disabled={isCreatingAccount} type="submit">{isCreatingAccount ? 'Creating…' : 'Create login account'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

export default StudentsPage
