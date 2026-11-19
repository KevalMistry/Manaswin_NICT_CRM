import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import api from '../services/api'
import type { RolePermission, MyPermissions } from '../types'

type BranchOption = {
  id: number
  name: string
  is_active: boolean
}

function PermissionsPage() {
  const [roles, setRoles] = useState<RolePermission[]>([])
  const [myPerms, setMyPerms] = useState<MyPermissions | null>(null)
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [scope, setScope] = useState('global')
  const [loading, setLoading] = useState(true)
  const [savingRoleId, setSavingRoleId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [matrix, setMatrix] = useState<Record<number, Record<string, boolean>>>({})

  const applyPermissions = useCallback((data: RolePermission[]) => {
    setRoles(data)

    const initialMatrix: Record<number, Record<string, boolean>> = {}
    for (const r of data) {
      initialMatrix[r.role_id] = {}
      for (const p of r.permissions) {
        initialMatrix[r.role_id][p.module_key] = p.can_access
      }
    }
    setMatrix(initialMatrix)
  }, [])

  const loadPermissions = useCallback(
    async (scopeValue: string) => {
      setLoading(true)
      setError('')
      try {
        const params = scopeValue === 'global' ? {} : { branch_id: Number(scopeValue) }
        const { data } = await api.get<RolePermission[]>('/api/permissions', { params })
        applyPermissions(data)
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 403) {
          setError('You do not have permission to view or manage role permissions.')
        } else {
          setError('Failed to load permissions. Ensure the backend server is running.')
        }
      } finally {
        setLoading(false)
      }
    },
    [applyPermissions],
  )

  const initialize = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const myResp = await api.get<MyPermissions>('/api/permissions/my-permissions')
      setMyPerms(myResp.data)

      const isSuperAdmin = myResp.data.role_name === 'Super Admin'
      let initialScope = 'global'

      if (isSuperAdmin) {
        try {
          const branchResp = await api.get<BranchOption[]>('/api/branches', {
            params: { limit: 100 },
          })
          setBranches(branchResp.data)
        } catch {
          // A Super Admin without the branches module can still manage the
          // global permission layer; the selector simply lists no branches.
          setBranches([])
        }
      } else if (myResp.data.branch_id != null) {
        initialScope = String(myResp.data.branch_id)
      }

      setScope(initialScope)
      await loadPermissions(initialScope)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        setError('You do not have permission to view or manage role permissions.')
      } else {
        setError('Failed to load permissions. Ensure the backend server is running.')
      }
      setLoading(false)
    }
  }, [loadPermissions])

  useEffect(() => {
    const timer = window.setTimeout(() => void initialize(), 0)
    return () => window.clearTimeout(timer)
  }, [initialize])

  async function changeScope(nextScope: string) {
    if (nextScope === scope) return
    setScope(nextScope)
    setSuccess('')
    await loadPermissions(nextScope)
  }

  function togglePermission(roleId: number, moduleKey: string) {
    setMatrix((prev) => ({
      ...prev,
      [roleId]: {
        ...prev[roleId],
        [moduleKey]: !prev[roleId]?.[moduleKey],
      },
    }))
    setSuccess('')
    setError('')
  }

  function scopeParams() {
    return scope === 'global' ? {} : { branch_id: Number(scope) }
  }

  function scopeLabel() {
    if (scope === 'global') return 'all branches (global)'
    const branch = branches.find((b) => String(b.id) === scope)
    if (branch) return branch.name
    if (myPerms?.branch_id != null && String(myPerms.branch_id) === scope) {
      return myPerms.branch_name ?? `branch #${scope}`
    }
    return `branch #${scope}`
  }

  async function saveRolePermissions(roleId: number) {
    setSavingRoleId(roleId)
    setError('')
    setSuccess('')
    try {
      const rolePayload = matrix[roleId]
      const { data } = await api.put<RolePermission>(
        `/api/permissions/${roleId}`,
        { permissions: rolePayload },
        { params: scopeParams() },
      )
      setRoles((prev) => prev.map((r) => (r.role_id === roleId ? data : r)))
      setSuccess(`Permissions updated for ${data.role_name} in ${scopeLabel()}.`)

      // Refresh stored user allowed modules if the edit affects the signed-in
      // account: same role and either the same branch or the global layer.
      const currentUser = JSON.parse(localStorage.getItem('current_user') ?? '{}')
      const ownScope =
        currentUser.branch_id != null ? String(currentUser.branch_id) : 'global'
      if (currentUser.role_id === roleId && ownScope === scope) {
        const allowed = Object.entries(rolePayload)
          .filter(([, v]) => v)
          .map(([k]) => k)
        currentUser.allowed_modules = allowed
        localStorage.setItem('current_user', JSON.stringify(currentUser))
      }
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to save permissions.')
      }
    } finally {
      setSavingRoleId(null)
    }
  }

  async function resetRole(roleId: number, roleName: string) {
    const target =
      scope === 'global'
        ? `the global defaults for ${roleName}`
        : `${roleName} in ${scopeLabel()} (inherits the global policy)`
    if (!window.confirm(`Reset permissions for ${target}?`)) return
    setSavingRoleId(roleId)
    setError('')
    setSuccess('')
    try {
      const { data } = await api.post<RolePermission>(
        `/api/permissions/${roleId}/reset`,
        null,
        { params: scopeParams() },
      )
      setRoles((prev) => prev.map((r) => (r.role_id === roleId ? data : r)))
      setMatrix((prev) => ({
        ...prev,
        [roleId]: Object.fromEntries(data.permissions.map((p) => [p.module_key, p.can_access])),
      }))
      setSuccess(
        scope === 'global'
          ? `Restored the built-in defaults for ${roleName}.`
          : `Removed overrides for ${roleName} in ${scopeLabel()}; it now inherits the global policy.`,
      )
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to reset permissions.')
      }
    } finally {
      setSavingRoleId(null)
    }
  }

  if (loading) {
    return (
      <div className="page-content">
        <div className="table-state">Loading role permissions…</div>
      </div>
    )
  }

  const isSuperAdmin = myPerms?.role_name === 'Super Admin'
  const isBranchAdmin = myPerms?.role_name === 'Branch Admin'

  // Extract all distinct module keys and labels from the first role
  const modules = roles[0]?.permissions ?? []

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">ACCESS CONTROL</span>
          <h1>Role &amp; Module Permissions</h1>
          <p>
            Customize which modules each role can access. Permissions are layered: built-in role
            defaults, then global overrides, then branch overrides. A branch override wins over the
            global policy for that branch only.
          </p>
        </div>
        <div className="heading-actions">
          <span className="role-scope-badge">
            {isSuperAdmin ? '👑 Super Admin Scope (All Roles)' : '🏢 Branch Admin Scope (Faculty, Staff, Counsellor)'}
          </span>
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      <section className="data-panel permissions-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">MODULE PERMISSIONS MATRIX</span>
            <h2>Role access rights</h2>
          </div>
          <div className="toolbar-controls">
            {isSuperAdmin ? (
              <div className="field" style={{ minWidth: 230, margin: 0 }}>
                <label htmlFor="permission-scope">Permission layer</label>
                <select
                  id="permission-scope"
                  value={scope}
                  onChange={(e) => void changeScope(e.target.value)}
                >
                  <option value="global">All branches — global policy</option>
                  {branches.map((branch) => (
                    <option key={branch.id} value={String(branch.id)}>
                      {branch.name}
                      {branch.is_active ? '' : ' (inactive)'}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="field" style={{ minWidth: 200, margin: 0 }}>
                <label htmlFor="permission-branch">Branch</label>
                <input
                  id="permission-branch"
                  type="text"
                  value={myPerms?.branch_name ?? 'Not assigned'}
                  readOnly
                />
              </div>
            )}
            <span className="result-count">{roles.length} roles configured</span>
          </div>
        </div>

        {scope !== 'global' && (
          <div className="permissions-footer-note" style={{ marginBottom: 14 }}>
            <span className="help-icon">ℹ</span>
            <div>
              <strong>Editing the {scopeLabel()} override layer.</strong>
              <p>
                Values shown include the global policy. Saving stores only this branch's overrides;
                resetting removes them so the branch inherits the global policy again.
              </p>
            </div>
          </div>
        )}

        <div className="table-wrap permissions-table-wrap">
          <table className="permissions-matrix-table">
            <thead>
              <tr>
                <th className="sticky-col">Role</th>
                {modules.map((m) => (
                  <th key={m.module_key} className="module-header-col">
                    <span className="module-header-label">{m.label}</span>
                    <small className="module-key-tag">`{m.module_key}`</small>
                  </th>
                ))}
                <th className="action-col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {roles.map((role) => {
                const isLocked = !role.can_edit
                const isSaving = savingRoleId === role.role_id

                return (
                  <tr key={role.role_id} className={isLocked ? 'role-locked-row' : ''}>
                    <td className="sticky-col">
                      <div className="role-name-cell">
                        <strong>{role.role_name}</strong>
                        {isLocked ? (
                          <span className="locked-pill">
                            {role.role_name === 'Super Admin' ? 'Full Access' : isBranchAdmin ? 'Super Admin Only' : 'Locked'}
                          </span>
                        ) : (
                          <span className="editable-pill">Customizable</span>
                        )}
                      </div>
                    </td>

                    {modules.map((m) => {
                      const isChecked = matrix[role.role_id]?.[m.module_key] ?? false
                      return (
                        <td key={m.module_key} className="perm-toggle-cell">
                          <label className={`toggle-switch ${isLocked ? 'disabled' : ''}`}>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              disabled={isLocked || isSaving}
                              onChange={() => togglePermission(role.role_id, m.module_key)}
                            />
                            <span className="toggle-slider" />
                          </label>
                        </td>
                      )
                    })}

                    <td className="action-col">
                      {role.can_edit ? (
                        <div className="row-actions">
                          <button
                            className="primary-button btn-sm"
                            disabled={isSaving}
                            onClick={() => void saveRolePermissions(role.role_id)}
                            type="button"
                          >
                            {isSaving ? 'Saving…' : 'Save'}
                          </button>
                          <button
                            className="secondary-button btn-sm"
                            disabled={isSaving}
                            onClick={() => void resetRole(role.role_id, role.role_name)}
                            type="button"
                          >
                            Reset
                          </button>
                        </div>
                      ) : (
                        <span className="text-muted-small">Fixed</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="permissions-footer-note">
          <span className="help-icon">ℹ</span>
          <div>
            <strong>How permission changes take effect:</strong>
            <p>
              When permissions are saved, API endpoints are immediately enforced. Users currently
              logged in will see their navigation menus updated on their next page load or
              navigation.
            </p>
          </div>
        </div>
      </section>
    </>
  )
}

export default PermissionsPage
