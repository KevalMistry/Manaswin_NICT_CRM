import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'

type ParentChild = {
  link_id: number
  student_id: number
  student_code: string
  student_name: string
  relationship: string
  is_primary: boolean
}

type ParentAccount = {
  user_id: number
  full_name: string
  email: string
  phone: string | null
  branch_id: number | null
  branch_name: string | null
  is_active: boolean
  created_at: string
  children: ParentChild[]
}

type StudentOption = {
  id: number
  student_code: string
  full_name: string
  branch_id: number
  parent_name: string | null
  parent_phone: string | null
}

const RELATIONSHIPS = ['Guardian', 'Father', 'Mother', 'Sibling', 'Other']

function ParentsPage() {
  const currentUser = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('current_user') ?? '{}') as {
        role_name?: string
        branch_id?: number | null
      }
    } catch {
      return {}
    }
  }, [])

  const [parents, setParents] = useState<ParentAccount[]>([])
  const [students, setStudents] = useState<StudentOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [phone, setPhone] = useState('')
  const [relationship, setRelationship] = useState('Guardian')
  const [studentId, setStudentId] = useState('')

  const [linkParent, setLinkParent] = useState<ParentAccount | null>(null)
  const [linkStudentId, setLinkStudentId] = useState('')
  const [linkRelationship, setLinkRelationship] = useState('Guardian')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [parentResponse, studentResponse] = await Promise.all([
        api.get<ParentAccount[]>('/api/parents'),
        api.get<StudentOption[]>('/api/students'),
      ])
      setParents(parentResponse.data)
      setStudents(studentResponse.data.filter((student) => student.id > 0))
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load parent accounts.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  function resetForm() {
    setFullName('')
    setEmail('')
    setPassword('')
    setPhone('')
    setRelationship('Guardian')
    setStudentId('')
  }

  async function createParent(event: React.FormEvent) {
    event.preventDefault()
    if (!studentId) {
      setError('Choose the student this parent should follow.')
      return
    }
    setBusy('create')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<ParentAccount>('/api/parents', {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        phone: phone.trim() || null,
        relationship,
        student_ids: [Number(studentId)],
      })
      setParents((current) => [...current, data].sort((a, b) => a.full_name.localeCompare(b.full_name)))
      setMessage(
        `Parent login created for ${data.full_name}. Share ${data.email} and the password you set with them directly.`,
      )
      resetForm()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to create the parent account.'))
    } finally {
      setBusy('')
    }
  }

  async function toggleActive(parent: ParentAccount) {
    setBusy(`active-${parent.user_id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<ParentAccount>(`/api/parents/${parent.user_id}`, {
        is_active: !parent.is_active,
      })
      setParents((current) =>
        current.map((item) => (item.user_id === data.user_id ? data : item)),
      )
      setMessage(`${data.full_name}'s login is now ${data.is_active ? 'active' : 'disabled'}.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to update the parent account.'))
    } finally {
      setBusy('')
    }
  }

  async function resetPassword(parent: ParentAccount) {
    const next = window.prompt(
      `Set a new password for ${parent.full_name} (at least 8 characters).`,
    )
    if (next === null) return
    if (next.length < 8) {
      setError('Passwords must be at least 8 characters long.')
      return
    }
    setBusy(`password-${parent.user_id}`)
    setError('')
    setMessage('')
    try {
      await api.post(`/api/parents/${parent.user_id}/password`, { password: next })
      setMessage(`Password updated for ${parent.full_name}.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to reset the password.'))
    } finally {
      setBusy('')
    }
  }

  async function unlinkChild(parent: ParentAccount, child: ParentChild) {
    if (!window.confirm(`Remove ${child.student_name} from ${parent.full_name}'s portal?`)) {
      return
    }
    setBusy(`unlink-${child.link_id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.delete<ParentAccount>(
        `/api/parents/${parent.user_id}/children/${child.student_id}`,
      )
      setParents((current) =>
        current.map((item) => (item.user_id === data.user_id ? data : item)),
      )
      setMessage(`${child.student_name} was removed from the portal.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to remove the student link.'))
    } finally {
      setBusy('')
    }
  }

  function openLinkModal(parent: ParentAccount) {
    setLinkParent(parent)
    const first = students.find(
      (student) => !parent.children.some((child) => child.student_id === student.id),
    )
    setLinkStudentId(first ? String(first.id) : '')
    setLinkRelationship(parent.children[0]?.relationship ?? 'Guardian')
    setError('')
  }

  async function linkChild(event: React.FormEvent) {
    event.preventDefault()
    if (!linkParent || !linkStudentId) return
    setBusy('link')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<ParentAccount>(
        `/api/parents/${linkParent.user_id}/children`,
        {
          student_id: Number(linkStudentId),
          relationship: linkRelationship,
        },
      )
      setParents((current) =>
        current.map((item) => (item.user_id === data.user_id ? data : item)),
      )
      setMessage(`Student linked to ${data.full_name}'s portal.`)
      setLinkParent(null)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to link that student.'))
    } finally {
      setBusy('')
    }
  }

  const linkOptions = linkParent
    ? students.filter(
        (student) =>
          !linkParent.children.some((child) => child.student_id === student.id),
      )
    : []

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">PARENTS</span>
          <h1>Guardian portal access</h1>
          <p>
            Create read-only parent logins and link them to one or more students.
            Parents only see the children connected here.
          </p>
        </div>
        <span className="result-count">
          {parents.length} account{parents.length === 1 ? '' : 's'} ·{' '}
          {currentUser.branch_id ? 'your branch' : 'all branches'}
        </span>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="data-panel lms-section-gap">
        <div className="section-title">
          <div>
            <span className="eyebrow">NEW ACCOUNT</span>
            <h2>Create a parent login</h2>
          </div>
        </div>
        <form className="parent-create-form" onSubmit={(event) => void createParent(event)}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="parent-name">Parent name</label>
              <input
                id="parent-name"
                onChange={(event) => setFullName(event.target.value)}
                placeholder="e.g. Rakesh Mehta"
                required
                value={fullName}
              />
            </div>
            <div className="field">
              <label htmlFor="parent-email">Login email</label>
              <input
                id="parent-email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="parent@example.com"
                required
                type="email"
                value={email}
              />
            </div>
            <div className="field">
              <label htmlFor="parent-password">Temporary password</label>
              <input
                id="parent-password"
                minLength={8}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 8 characters"
                required
                type="password"
                value={password}
              />
            </div>
            <div className="field">
              <label htmlFor="parent-phone">Phone</label>
              <input
                id="parent-phone"
                onChange={(event) => setPhone(event.target.value)}
                placeholder="+91 …"
                value={phone}
              />
            </div>
            <div className="field">
              <label htmlFor="parent-student">Child</label>
              <select
                id="parent-student"
                onChange={(event) => setStudentId(event.target.value)}
                required
                value={studentId}
              >
                <option value="">Select a student</option>
                {students.map((student) => (
                  <option key={student.id} value={student.id}>
                    {student.full_name} ({student.student_code})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="parent-relationship">Relationship</label>
              <select
                id="parent-relationship"
                onChange={(event) => setRelationship(event.target.value)}
                value={relationship}
              >
                {RELATIONSHIPS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="modal-actions parent-form-actions">
            <button className="primary-button" disabled={busy === 'create'} type="submit">
              {busy === 'create' ? 'Creating…' : 'Create parent login'}
            </button>
          </div>
          <p className="notification-hint">
            Credentials are not emailed automatically. Share the login with the
            parent after saving; they can change the password from their profile.
          </p>
        </form>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">ACCOUNTS</span>
            <h2>Existing parent logins</h2>
          </div>
          <span className="result-count">{parents.length} total</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Parent</th>
                <th>Contact</th>
                <th>Branch</th>
                <th>Children</th>
                <th>Login</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {parents.map((parent) => (
                <tr key={parent.user_id}>
                  <td>
                    <strong>{parent.full_name}</strong>
                    <small className="muted-block">{parent.email}</small>
                  </td>
                  <td>{parent.phone ?? '—'}</td>
                  <td>{parent.branch_name ?? '—'}</td>
                  <td>
                    <div className="parent-child-chips">
                      {parent.children.map((child) => (
                        <span className="parent-child-chip" key={child.link_id}>
                          <span>
                            {child.student_name}
                            <small>{child.relationship}</small>
                          </span>
                          <button
                            aria-label={`Remove ${child.student_name}`}
                            disabled={busy === `unlink-${child.link_id}`}
                            onClick={() => void unlinkChild(parent, child)}
                            type="button"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {!parent.children.length && <span className="muted">No children</span>}
                    </div>
                  </td>
                  <td>
                    <span
                      className={`status-pill ${parent.is_active ? 'active-status' : 'inactive-status'}`}
                    >
                      <i />
                      {parent.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button onClick={() => openLinkModal(parent)} type="button">
                        Add child
                      </button>
                      <button
                        disabled={busy === `password-${parent.user_id}`}
                        onClick={() => void resetPassword(parent)}
                        type="button"
                      >
                        Reset password
                      </button>
                      <button
                        className={parent.is_active ? 'danger-action' : ''}
                        disabled={busy === `active-${parent.user_id}`}
                        onClick={() => void toggleActive(parent)}
                        type="button"
                      >
                        {parent.is_active ? 'Disable' : 'Enable'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!parents.length && !loading && (
            <div className="table-state">
              <strong>No parent logins yet</strong>
              <p>Create the first account above and link it to a student.</p>
            </div>
          )}
          {loading && <div className="table-state">Loading parent accounts…</div>}
        </div>
      </section>

      {linkParent && (
        <div className="modal-backdrop" onClick={() => setLinkParent(null)}>
          <form
            className="modal-card"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void linkChild(event)}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">LINK STUDENT</span>
                <h2>{linkParent.full_name}</h2>
              </div>
              <button
                className="close-button"
                onClick={() => setLinkParent(null)}
                type="button"
              >
                ×
              </button>
            </div>
            <div className="form-grid">
              <div className="field full-field">
                <label htmlFor="link-student">Student</label>
                <select
                  id="link-student"
                  onChange={(event) => setLinkStudentId(event.target.value)}
                  required
                  value={linkStudentId}
                >
                  <option value="">Select a student</option>
                  {linkOptions.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.full_name} ({student.student_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="field full-field">
                <label htmlFor="link-relationship">Relationship</label>
                <select
                  id="link-relationship"
                  onChange={(event) => setLinkRelationship(event.target.value)}
                  value={linkRelationship}
                >
                  {RELATIONSHIPS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {!linkOptions.length && (
              <div className="inline-error">
                Every visible student is already linked to this parent.
              </div>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => setLinkParent(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className="primary-button"
                disabled={!linkStudentId || busy === 'link'}
                type="submit"
              >
                {busy === 'link' ? 'Linking…' : 'Link student'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

export default ParentsPage
