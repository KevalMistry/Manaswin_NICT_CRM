import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'

type User = { id: number; full_name: string; email: string; phone: string | null; role_id: number; role_name: string; branch_id: number | null; is_active: boolean }
type Branch = { id: number; name: string; code: string; is_active: boolean }
type Responsibility = { id: number; title: string; department: string; assigned_to_id: number; branch_id: number; due_date: string | null; status: string }
type Summary = { assigned_responsibilities: number; completed_responsibilities: number; overdue_responsibilities: number; follow_ups_completed: number; admissions_handled: number; latest_rating: number | null }

const roleOptions = [{ id: 2, label: 'Branch Admin' }, { id: 3, label: 'Faculty' }, { id: 5, label: 'Staff' }, { id: 6, label: 'Counsellor' }]
const performanceRoles = new Set(['Faculty', 'Staff', 'Counsellor'])
const emptyUser = { full_name: '', email: '', password: '', phone: '', role_id: '', branch_id: '' }
const emptyResponsibility = { title: '', department: '', description: '', assigned_to_id: '', branch_id: '', due_date: '' }

function StaffPage() {
  const [users, setUsers] = useState<User[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [responsibilities, setResponsibilities] = useState<Responsibility[]>([])
  const [userForm, setUserForm] = useState(emptyUser)
  const [responsibilityForm, setResponsibilityForm] = useState(emptyResponsibility)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [isUserOpen, setIsUserOpen] = useState(false)
  const [showTemporaryPassword, setShowTemporaryPassword] = useState(false)
  const [isResponsibilityOpen, setIsResponsibilityOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [selectedUser, setSelectedUser] = useState<number | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({ full_name: '', email: '', phone: '' })
  const [isEditingUser, setIsEditingUser] = useState(false)
  const [editError, setEditError] = useState('')
  const currentUser = JSON.parse(localStorage.getItem('current_user') ?? '{}') as { role_name?: string }
  const canManageBranchAdmins = currentUser.role_name === 'Super Admin'
  const availableRoles = canManageBranchAdmins ? roleOptions : roleOptions.filter((role) => role.label !== 'Branch Admin')

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [usersResponse, branchesResponse, responsibilitiesResponse] = await Promise.all([
        api.get<User[]>('/api/staff/users', { params: { include_inactive: showInactive } }),
        api.get<Branch[]>('/api/branches'),
        api.get<Responsibility[]>('/api/staff/responsibilities'),
      ])
      setUsers(usersResponse.data)
      setBranches(branchesResponse.data)
      setResponsibilities(responsibilitiesResponse.data)
    } catch {
      setError('Could not load staff and responsibility data.')
    } finally {
      setIsLoading(false)
    }
  }, [showInactive])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  async function viewPerformance(userId: number) {
    setSelectedUser(userId)
    try {
      const { data } = await api.get<Summary>(`/api/staff/performance/${userId}`)
      setSummary(data)
    } catch {
      setError('Could not load this performance summary.')
    }
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    try {
      await api.post('/api/staff/users', { ...userForm, role_id: Number(userForm.role_id), branch_id: Number(userForm.branch_id), phone: userForm.phone || null })
      setIsUserOpen(false)
      setUserForm(emptyUser)
      await load()
    } catch {
      setError('Unable to create this account. Check the email, role, branch, and password.')
    } finally {
      setIsSaving(false)
    }
  }

  async function createResponsibility(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    try {
      await api.post('/api/staff/responsibilities', { ...responsibilityForm, assigned_to_id: Number(responsibilityForm.assigned_to_id), branch_id: Number(responsibilityForm.branch_id), due_date: responsibilityForm.due_date || null, description: responsibilityForm.description || null })
      setIsResponsibilityOpen(false)
      setResponsibilityForm(emptyResponsibility)
      await load()
    } catch {
      setError('Unable to assign this responsibility.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deactivateUser(user: User) {
    if (!window.confirm(`Deactivate ${user.full_name}'s account?`)) return
    try {
      await api.patch(`/api/staff/users/${user.id}`, { is_active: false })
      await load()
    } catch {
      setError('Unable to deactivate this account.')
    }
  }

  async function reactivateUser(user: User) {
    try {
      await api.patch(`/api/staff/users/${user.id}`, { is_active: true })
      await load()
    } catch {
      setError('Unable to reactivate this account.')
    }
  }

  async function deleteUser(user: User) {
    if (!window.confirm(`Permanently delete ${user.full_name}'s account and attached responsibilities? This cannot be undone.`)) return
    try {
      await api.delete(`/api/staff/users/${user.id}`)
      await load()
    } catch {
      setError('Unable to permanently delete this account.')
    }
  }

  function openEditUser(user: User) {
    setEditingUser(user)
    setEditForm({ full_name: user.full_name, email: user.email, phone: user.phone ?? '' })
    setEditError('')
  }

  async function submitEditUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingUser) return
    setIsEditingUser(true)
    setEditError('')
    try {
      await api.patch(`/api/staff/users/${editingUser.id}`, {
        full_name: editForm.full_name.trim(),
        email: editForm.email.trim(),
        phone: editForm.phone.trim() || null,
      })
      setEditingUser(null)
      await load()
    } catch {
      setEditError('Unable to update this account. Ensure the email is valid and unique.')
    } finally {
      setIsEditingUser(false)
    }
  }

  const roleName = (user: User) => user.role_name || (roleOptions.find((role) => role.id === user.role_id)?.label ?? 'User')
  const userName = (id: number) => users.find((user) => user.id === id)?.full_name ?? `User #${id}`
  const branchName = (id: number | null) => branches.find((branch) => branch.id === id)?.name ?? 'Unassigned'

  return (
    <>
      <div className="page-heading module-heading"><div><span className="eyebrow">USER MANAGEMENT</span><h1>{canManageBranchAdmins ? 'Administrators & team' : 'Branch team'}</h1><p>{canManageBranchAdmins ? 'Manage Branch Admin, Faculty, Staff, and Counsellor accounts across the institute.' : 'Manage Faculty, Staff, and Counsellor accounts in your assigned branch.'}</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => setIsResponsibilityOpen(true)} type="button">+ Assign responsibility</button><button className="primary-button" onClick={() => setIsUserOpen(true)} type="button">+ Add account</button></div></div>
      {error && <div className="inline-error">{error}</div>}
      <section className="data-panel"><div className="section-title"><div><span className="eyebrow">MANAGED ACCOUNTS</span><h2>Administrators, faculty, staff & counsellors</h2></div><div className="section-actions"><label className="checkbox-label"><input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} /> Show inactive</label><span className="result-count">{users.length} accounts</span></div></div>
        {isLoading ? <div className="table-state">Loading team members…</div> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Branch</th><th>Contact</th><th>Actions</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><div className="branch-name"><span className="branch-avatar">{user.full_name.slice(0, 1).toUpperCase()}</span><span><strong>{user.full_name}</strong><small>{user.email}</small></span></div></td><td>{roleName(user)}</td><td>{branchName(user.branch_id)}</td><td>{user.phone || '—'}</td><td><div className="row-actions">{performanceRoles.has(roleName(user)) && <button className="row-link" onClick={() => void viewPerformance(user.id)} type="button">Performance</button>}<button className="row-link" onClick={() => openEditUser(user)} type="button">Edit</button>{user.is_active ? <button className="row-link" onClick={() => void deactivateUser(user)} type="button">Deactivate</button> : <button className="row-link" onClick={() => void reactivateUser(user)} type="button">Reactivate</button>}<button className="row-link danger-action" onClick={() => void deleteUser(user)} type="button">Delete permanently</button></div></td></tr>)}</tbody></table></div>}
      </section>
      <section className="data-panel responsibility-panel"><div className="section-title"><div><span className="eyebrow">RESPONSIBILITIES</span><h2>Department responsibilities</h2></div></div><div className="table-wrap"><table><thead><tr><th>Responsibility</th><th>Department</th><th>Assigned to</th><th>Due date</th><th>Status</th></tr></thead><tbody>{responsibilities.map((item) => <tr key={item.id}><td><strong>{item.title}</strong></td><td>{item.department}</td><td>{userName(item.assigned_to_id)}</td><td>{item.due_date || 'No deadline'}</td><td><span className="status-pill active-status">{item.status.replace('_', ' ')}</span></td></tr>)}</tbody></table></div></section>
      {summary && selectedUser && <section className="performance-card"><div><span className="eyebrow">PERFORMANCE SUMMARY</span><h2>{userName(selectedUser)}</h2></div><div className="metric-row"><div><strong>{summary.assigned_responsibilities}</strong><span>Assigned</span></div><div><strong>{summary.completed_responsibilities}</strong><span>Completed</span></div><div><strong>{summary.overdue_responsibilities}</strong><span>Overdue</span></div><div><strong>{summary.follow_ups_completed}</strong><span>Follow-ups</span></div><div><strong>{summary.admissions_handled}</strong><span>Admissions</span></div><div><strong>{summary.latest_rating ?? '—'}</strong><span>Rating / 5</span></div></div></section>}
      {isUserOpen && <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true"><div className="modal-header"><div><span className="eyebrow">NEW ACCOUNT</span><h2>Add account</h2></div><button className="close-button" onClick={() => setIsUserOpen(false)} type="button">×</button></div><form onSubmit={createUser}><div className="form-grid"><div className="field full-field"><label htmlFor="team-name">Full name</label><input id="team-name" value={userForm.full_name} onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })} required /></div><div className="field"><label htmlFor="team-email">Email</label><input id="team-email" type="email" value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} required /></div>      <div className="field"><label htmlFor="team-password">Temporary password</label><div className="password-input"><input id="team-password" type={showTemporaryPassword ? 'text' : 'password'} minLength={8} value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })} required /><button onClick={() => setShowTemporaryPassword((value) => !value)} type="button">{showTemporaryPassword ? 'Hide' : 'Show'}</button></div></div><div className="field"><label htmlFor="team-role">Role</label><select id="team-role" value={userForm.role_id} onChange={(event) => setUserForm({ ...userForm, role_id: event.target.value })} required><option value="">Select role</option>{availableRoles.map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}</select></div><div className="field"><label htmlFor="team-branch">Branch</label><select id="team-branch" value={userForm.branch_id} onChange={(event) => setUserForm({ ...userForm, branch_id: event.target.value })} required><option value="">Select branch</option>{branches.filter((branch) => branch.is_active).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></div></div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsUserOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Creating…' : 'Create account'}</button></div></form></div></div>}
      {isResponsibilityOpen && <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true"><div className="modal-header"><div><span className="eyebrow">ASSIGN WORK</span><h2>Assign responsibility</h2></div><button className="close-button" onClick={() => setIsResponsibilityOpen(false)} type="button">×</button></div><form onSubmit={createResponsibility}><div className="form-grid"><div className="field full-field"><label htmlFor="responsibility-title">Title</label><input id="responsibility-title" value={responsibilityForm.title} onChange={(event) => setResponsibilityForm({ ...responsibilityForm, title: event.target.value })} required /></div><div className="field"><label htmlFor="responsibility-department">Department</label><input id="responsibility-department" placeholder="Admissions, counselling…" value={responsibilityForm.department} onChange={(event) => setResponsibilityForm({ ...responsibilityForm, department: event.target.value })} required /></div><div className="field"><label htmlFor="responsibility-assignee">Assign to</label><select id="responsibility-assignee" value={responsibilityForm.assigned_to_id} onChange={(event) => setResponsibilityForm({ ...responsibilityForm, assigned_to_id: event.target.value })} required><option value="">Select member</option>{users.filter((user) => performanceRoles.has(roleName(user))).map((user) => <option key={user.id} value={user.id}>{user.full_name} ({roleName(user)})</option>)}</select></div><div className="field"><label htmlFor="responsibility-branch">Branch</label><select id="responsibility-branch" value={responsibilityForm.branch_id} onChange={(event) => setResponsibilityForm({ ...responsibilityForm, branch_id: event.target.value })} required><option value="">Select branch</option>{branches.filter((branch) => branch.is_active).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></div><div className="field"><label htmlFor="responsibility-due">Due date</label><input id="responsibility-due" type="date" value={responsibilityForm.due_date} onChange={(event) => setResponsibilityForm({ ...responsibilityForm, due_date: event.target.value })} /></div></div><div className="modal-actions"><button className="secondary-button" onClick={() => setIsResponsibilityOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Assigning…' : 'Assign responsibility'}</button></div></form></div></div>}
      {editingUser && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setEditingUser(null) }}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="edit-user-title">
            <div className="modal-header">
              <div>
                <span className="eyebrow">EDIT ACCOUNT</span>
                <h2 id="edit-user-title">Edit {roleName(editingUser)}</h2>
              </div>
              <button className="close-button" onClick={() => setEditingUser(null)} type="button">×</button>
            </div>
            {editError && <div className="inline-error">{editError}</div>}
            <form onSubmit={submitEditUser}>
              <div className="form-grid">
                <div className="field full-field">
                  <label htmlFor="edit-name">Full name</label>
                  <input
                    id="edit-name"
                    value={editForm.full_name}
                    onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                    required
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="edit-email">Email address</label>
                  <input
                    id="edit-email"
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                    required
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="edit-phone">Phone number</label>
                  <input
                    id="edit-phone"
                    value={editForm.phone}
                    onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                    placeholder="+91…"
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setEditingUser(null)} type="button">Cancel</button>
                <button className="primary-button" disabled={isEditingUser} type="submit">{isEditingUser ? 'Saving…' : 'Save changes'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

export default StaffPage
