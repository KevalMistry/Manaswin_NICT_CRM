import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'

type Franchise = {
  id: number
  branch_id: number
  branch_name: string
  branch_code: string
  owner_name: string
  owner_phone: string | null
  owner_email: string | null
  agreement_start: string
  agreement_end: string | null
  royalty_percent: string
  status: string
  notes: string | null
  students: number
  revenue: string
  royalty_paid: string
  royalty_due: string
  created_at: string
}

type Royalty = {
  id: number
  franchise_id: number
  branch_name: string
  owner_name: string
  amount: string
  payment_date: string
  period_from: string
  period_to: string
  reference: string | null
  notes: string | null
  recorded_by: string | null
  created_at: string
}

type Summary = {
  franchises: number
  active_franchises: number
  students: number
  revenue: string
  royalty_expected: string
  royalty_paid: string
  royalty_due: string
}

type BranchOption = { id: number; name: string; code: string }

const STATUSES = ['active', 'suspended', 'terminated']

function inr(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '₹0'
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function monthStart(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

function statusClass(status: string): string {
  if (status === 'active') return 'active-status'
  if (status === 'suspended') return 'pending-status'
  return 'inactive-status'
}

function FranchisePage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [franchises, setFranchises] = useState<Franchise[]>([])
  const [royalties, setRoyalties] = useState<Royalty[]>([])
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [tab, setTab] = useState<'profiles' | 'royalties'>('profiles')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')

  const [profileForm, setProfileForm] = useState({
    branch_id: '',
    owner_name: '',
    owner_phone: '',
    owner_email: '',
    agreement_start: today(),
    agreement_end: '',
    royalty_percent: '10',
    status: 'active',
    notes: '',
  })
  const [royaltyForm, setRoyaltyForm] = useState({
    franchise_id: '',
    amount: '',
    payment_date: today(),
    period_from: monthStart(),
    period_to: today(),
    reference: '',
    notes: '',
  })

  const [editingProfile, setEditingProfile] = useState<Franchise | null>(null)
  const [profileDraft, setProfileDraft] = useState({
    owner_name: '',
    owner_phone: '',
    owner_email: '',
    agreement_start: '',
    agreement_end: '',
    royalty_percent: '',
    status: 'active',
    notes: '',
  })
  const [editingRoyalty, setEditingRoyalty] = useState<Royalty | null>(null)
  const [royaltyDraft, setRoyaltyDraft] = useState({
    amount: '',
    payment_date: '',
    period_from: '',
    period_to: '',
    reference: '',
    notes: '',
  })

  const availableBranches = useMemo(() => {
    const taken = new Set(franchises.map((item) => item.branch_id))
    return branches.filter((branch) => !taken.has(branch.id))
  }, [branches, franchises])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryRes, profileRes, royaltyRes, branchRes] = await Promise.all([
        api.get<Summary>('/api/franchises/summary'),
        api.get<Franchise[]>('/api/franchises/profiles'),
        api.get<Royalty[]>('/api/franchises/royalties'),
        api.get<BranchOption[]>('/api/branches').catch(() => ({ data: [] as BranchOption[] })),
      ])
      setSummary(summaryRes.data)
      setFranchises(profileRes.data)
      setRoyalties(royaltyRes.data)
      setBranches(branchRes.data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load franchise management.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  function flash(text: string) {
    setMessage(text)
    setError('')
  }

  function fail(requestError: unknown, fallback: string) {
    setError(apiErrorMessage(requestError, fallback))
    setMessage('')
  }

  async function refreshSummary() {
    const { data } = await api.get<Summary>('/api/franchises/summary')
    setSummary(data)
  }

  async function createProfile(event: React.FormEvent) {
    event.preventDefault()
    setBusy('profile')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Franchise>('/api/franchises/profiles', {
        branch_id: Number(profileForm.branch_id),
        owner_name: profileForm.owner_name.trim(),
        owner_phone: profileForm.owner_phone.trim() || null,
        owner_email: profileForm.owner_email.trim() || null,
        agreement_start: profileForm.agreement_start,
        agreement_end: profileForm.agreement_end || null,
        royalty_percent: profileForm.royalty_percent || '0',
        status: profileForm.status,
        notes: profileForm.notes.trim() || null,
      })
      setFranchises((current) => [...current, data])
      setProfileForm((current) => ({
        ...current,
        branch_id: '',
        owner_name: '',
        owner_phone: '',
        owner_email: '',
        agreement_end: '',
        notes: '',
      }))
      flash(`${data.branch_name} franchise profile created.`)
      await refreshSummary()
    } catch (requestError) {
      fail(requestError, 'Unable to create the franchise profile.')
    } finally {
      setBusy('')
    }
  }

  function openProfileEditor(profile: Franchise) {
    setEditingProfile(profile)
    setProfileDraft({
      owner_name: profile.owner_name,
      owner_phone: profile.owner_phone ?? '',
      owner_email: profile.owner_email ?? '',
      agreement_start: profile.agreement_start,
      agreement_end: profile.agreement_end ?? '',
      royalty_percent: profile.royalty_percent,
      status: profile.status,
      notes: profile.notes ?? '',
    })
  }

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault()
    if (!editingProfile) return
    setBusy(`profile-${editingProfile.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Franchise>(
        `/api/franchises/profiles/${editingProfile.id}`,
        {
          owner_name: profileDraft.owner_name.trim(),
          owner_phone: profileDraft.owner_phone.trim() || null,
          owner_email: profileDraft.owner_email.trim() || null,
          agreement_start: profileDraft.agreement_start,
          agreement_end: profileDraft.agreement_end || null,
          royalty_percent: profileDraft.royalty_percent,
          status: profileDraft.status,
          notes: profileDraft.notes.trim() || null,
        },
      )
      setFranchises((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      setEditingProfile(null)
      flash('Franchise profile updated.')
      await refreshSummary()
    } catch (requestError) {
      fail(requestError, 'Unable to update the franchise profile.')
    } finally {
      setBusy('')
    }
  }

  async function deleteProfile(profile: Franchise) {
    if (!window.confirm(`Delete the franchise profile for ${profile.branch_name}?`)) return
    setBusy(`profile-${profile.id}`)
    setError('')
    try {
      await api.delete(`/api/franchises/profiles/${profile.id}`)
      setFranchises((current) => current.filter((item) => item.id !== profile.id))
      setRoyalties((current) => current.filter((item) => item.franchise_id !== profile.id))
      flash('Franchise profile removed.')
      await refreshSummary()
    } catch (requestError) {
      fail(requestError, 'Unable to delete the franchise profile.')
    } finally {
      setBusy('')
    }
  }

  async function createRoyalty(event: React.FormEvent) {
    event.preventDefault()
    setBusy('royalty')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Royalty>('/api/franchises/royalties', {
        franchise_id: Number(royaltyForm.franchise_id),
        amount: royaltyForm.amount,
        payment_date: royaltyForm.payment_date,
        period_from: royaltyForm.period_from,
        period_to: royaltyForm.period_to,
        reference: royaltyForm.reference.trim() || null,
        notes: royaltyForm.notes.trim() || null,
      })
      setRoyalties((current) => [data, ...current])
      setRoyaltyForm((current) => ({
        ...current,
        amount: '',
        reference: '',
        notes: '',
      }))
      flash(`Royalty of ${inr(data.amount)} recorded.`)
      await Promise.all([refreshSummary(), refreshProfiles()])
    } catch (requestError) {
      fail(requestError, 'Unable to record the royalty payment.')
    } finally {
      setBusy('')
    }
  }

  async function refreshProfiles() {
    const { data } = await api.get<Franchise[]>('/api/franchises/profiles')
    setFranchises(data)
  }

  function openRoyaltyEditor(royalty: Royalty) {
    setEditingRoyalty(royalty)
    setRoyaltyDraft({
      amount: royalty.amount,
      payment_date: royalty.payment_date,
      period_from: royalty.period_from,
      period_to: royalty.period_to,
      reference: royalty.reference ?? '',
      notes: royalty.notes ?? '',
    })
  }

  async function saveRoyalty(event: React.FormEvent) {
    event.preventDefault()
    if (!editingRoyalty) return
    setBusy(`royalty-${editingRoyalty.id}`)
    setError('')
    setMessage('')
    try {
      const { data } = await api.patch<Royalty>(
        `/api/franchises/royalties/${editingRoyalty.id}`,
        {
          amount: royaltyDraft.amount,
          payment_date: royaltyDraft.payment_date,
          period_from: royaltyDraft.period_from,
          period_to: royaltyDraft.period_to,
          reference: royaltyDraft.reference.trim() || null,
          notes: royaltyDraft.notes.trim() || null,
        },
      )
      setRoyalties((current) =>
        current.map((item) => (item.id === data.id ? data : item)),
      )
      setEditingRoyalty(null)
      flash('Royalty payment updated.')
      await Promise.all([refreshSummary(), refreshProfiles()])
    } catch (requestError) {
      fail(requestError, 'Unable to update the royalty payment.')
    } finally {
      setBusy('')
    }
  }

  async function deleteRoyalty(royalty: Royalty) {
    if (!window.confirm(`Delete the royalty payment of ${inr(royalty.amount)}?`)) return
    setBusy(`royalty-${royalty.id}`)
    setError('')
    try {
      await api.delete(`/api/franchises/royalties/${royalty.id}`)
      setRoyalties((current) => current.filter((item) => item.id !== royalty.id))
      flash('Royalty payment removed.')
      await Promise.all([refreshSummary(), refreshProfiles()])
    } catch (requestError) {
      fail(requestError, 'Unable to delete the royalty payment.')
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">FRANCHISE MANAGEMENT</span>
          <h1>Head-office franchise control</h1>
          <p>
            See every franchise branch, its revenue and royalty position, then
            record settlements as they arrive.
          </p>
        </div>
        <span className="result-count">
          {summary?.active_franchises ?? 0} active of {summary?.franchises ?? 0}
        </span>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="metric-grid finance-metrics">
        <article className="metric-card">
          <div className="metric-label">Franchises</div>
          <div className="metric-value">{summary?.franchises ?? 0}</div>
          <div className="metric-detail">{summary?.active_franchises ?? 0} active</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Students</div>
          <div className="metric-value">{summary?.students ?? 0}</div>
          <div className="metric-detail">Across franchise branches</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Revenue</div>
          <div className="metric-value">{inr(summary?.revenue)}</div>
          <div className="metric-detail">Fees collected</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Royalty expected</div>
          <div className="metric-value">{inr(summary?.royalty_expected)}</div>
          <div className="metric-detail">As per agreements</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Royalty paid</div>
          <div className="metric-value">{inr(summary?.royalty_paid)}</div>
          <div className="metric-detail">Settled by head office</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Royalty due</div>
          <div className="metric-value">{inr(summary?.royalty_due)}</div>
          <div className="metric-detail">Outstanding balance</div>
        </article>
      </section>

      <div className="module-tabs">
        <button
          className={tab === 'profiles' ? 'active-tab' : ''}
          onClick={() => setTab('profiles')}
          type="button"
        >
          Franchise profiles <span>{franchises.length}</span>
        </button>
        <button
          className={tab === 'royalties' ? 'active-tab' : ''}
          onClick={() => setTab('royalties')}
          type="button"
        >
          Royalty settlements <span>{royalties.length}</span>
        </button>
      </div>

      {tab === 'profiles' && (
        <>
          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">NEW FRANCHISE</span>
                <h2>Link a branch to a franchise owner</h2>
              </div>
              <span className="result-count">{availableBranches.length} branches available</span>
            </div>
            <form className="placement-form-block" onSubmit={(event) => void createProfile(event)}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="franchise-branch">Branch</label>
                  <select
                    id="franchise-branch"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, branch_id: event.target.value }))
                    }
                    required
                    value={profileForm.branch_id}
                  >
                    <option value="">Select a branch</option>
                    {availableBranches.map((branch) => (
                      <option key={branch.id} value={branch.id}>
                        {branch.name} ({branch.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="franchise-owner">Owner name</label>
                  <input
                    id="franchise-owner"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, owner_name: event.target.value }))
                    }
                    required
                    value={profileForm.owner_name}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-phone">Owner phone</label>
                  <input
                    id="franchise-phone"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, owner_phone: event.target.value }))
                    }
                    value={profileForm.owner_phone}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-email">Owner email</label>
                  <input
                    id="franchise-email"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, owner_email: event.target.value }))
                    }
                    type="email"
                    value={profileForm.owner_email}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-start">Agreement start</label>
                  <input
                    id="franchise-start"
                    onChange={(event) =>
                      setProfileForm((current) => ({
                        ...current,
                        agreement_start: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={profileForm.agreement_start}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-end">Agreement end</label>
                  <input
                    id="franchise-end"
                    onChange={(event) =>
                      setProfileForm((current) => ({
                        ...current,
                        agreement_end: event.target.value,
                      }))
                    }
                    type="date"
                    value={profileForm.agreement_end}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-royalty">Royalty %</label>
                  <input
                    id="franchise-royalty"
                    max={100}
                    min={0}
                    onChange={(event) =>
                      setProfileForm((current) => ({
                        ...current,
                        royalty_percent: event.target.value,
                      }))
                    }
                    step="0.01"
                    type="number"
                    value={profileForm.royalty_percent}
                  />
                </div>
                <div className="field">
                  <label htmlFor="franchise-status">Status</label>
                  <select
                    id="franchise-status"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, status: event.target.value }))
                    }
                    value={profileForm.status}
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status.charAt(0).toUpperCase() + status.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field full-field">
                  <label htmlFor="franchise-notes">Notes</label>
                  <textarea
                    id="franchise-notes"
                    onChange={(event) =>
                      setProfileForm((current) => ({ ...current, notes: event.target.value }))
                    }
                    rows={2}
                    value={profileForm.notes}
                  />
                </div>
              </div>
              <div className="placement-form-actions">
                <button
                  className="primary-button"
                  disabled={busy === 'profile' || !availableBranches.length}
                  type="submit"
                >
                  {busy === 'profile' ? 'Saving…' : 'Create franchise'}
                </button>
              </div>
            </form>
          </section>

          <section className="data-panel finance-table-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">FRANCHISE NETWORK</span>
                <h2>Branch agreements</h2>
              </div>
              <span className="result-count">{franchises.length} profiles</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Branch</th>
                    <th>Owner</th>
                    <th>Agreement</th>
                    <th>Royalty %</th>
                    <th>Students</th>
                    <th>Revenue</th>
                    <th>Paid</th>
                    <th>Due</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {franchises.map((profile) => (
                    <tr key={profile.id}>
                      <td>
                        <strong>{profile.branch_name}</strong>
                        <small className="muted-block">{profile.branch_code}</small>
                      </td>
                      <td>
                        {profile.owner_name}
                        <small className="muted-block">
                          {profile.owner_phone ?? profile.owner_email ?? '—'}
                        </small>
                      </td>
                      <td>
                        {profile.agreement_start}
                        <small className="muted-block">
                          {profile.agreement_end ? `to ${profile.agreement_end}` : 'open-ended'}
                        </small>
                      </td>
                      <td>{Number(profile.royalty_percent).toFixed(2)}%</td>
                      <td>{profile.students}</td>
                      <td>{inr(profile.revenue)}</td>
                      <td>{inr(profile.royalty_paid)}</td>
                      <td>{inr(profile.royalty_due)}</td>
                      <td>
                        <span className={`status-pill ${statusClass(profile.status)}`}>
                          <i />
                          {profile.status.charAt(0).toUpperCase() + profile.status.slice(1)}
                        </span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button onClick={() => openProfileEditor(profile)} type="button">
                            Edit
                          </button>
                          <button
                            className="danger-action"
                            disabled={busy === `profile-${profile.id}`}
                            onClick={() => void deleteProfile(profile)}
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
              {!franchises.length && (
                <div className="table-state">
                  {loading ? 'Loading franchises…' : 'No franchise profiles yet.'}
                </div>
              )}
            </div>
          </section>
        </>
      )}

      {tab === 'royalties' && (
        <>
          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">RECORD SETTLEMENT</span>
                <h2>Royalty received from a franchise</h2>
              </div>
            </div>
            <form className="placement-form-block" onSubmit={(event) => void createRoyalty(event)}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="royalty-franchise">Franchise</label>
                  <select
                    id="royalty-franchise"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({
                        ...current,
                        franchise_id: event.target.value,
                      }))
                    }
                    required
                    value={royaltyForm.franchise_id}
                  >
                    <option value="">Select a franchise</option>
                    {franchises.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {profile.branch_name} · {profile.owner_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="royalty-amount">Amount (₹)</label>
                  <input
                    id="royalty-amount"
                    min={0}
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({ ...current, amount: event.target.value }))
                    }
                    required
                    step="0.01"
                    type="number"
                    value={royaltyForm.amount}
                  />
                </div>
                <div className="field">
                  <label htmlFor="royalty-date">Payment date</label>
                  <input
                    id="royalty-date"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({
                        ...current,
                        payment_date: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyForm.payment_date}
                  />
                </div>
                <div className="field">
                  <label htmlFor="royalty-reference">Reference</label>
                  <input
                    id="royalty-reference"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({ ...current, reference: event.target.value }))
                    }
                    placeholder="Receipt or transfer reference"
                    value={royaltyForm.reference}
                  />
                </div>
                <div className="field">
                  <label htmlFor="royalty-from">Period from</label>
                  <input
                    id="royalty-from"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({
                        ...current,
                        period_from: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyForm.period_from}
                  />
                </div>
                <div className="field">
                  <label htmlFor="royalty-to">Period to</label>
                  <input
                    id="royalty-to"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({
                        ...current,
                        period_to: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyForm.period_to}
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="royalty-notes">Notes</label>
                  <textarea
                    id="royalty-notes"
                    onChange={(event) =>
                      setRoyaltyForm((current) => ({ ...current, notes: event.target.value }))
                    }
                    rows={2}
                    value={royaltyForm.notes}
                  />
                </div>
              </div>
              <div className="placement-form-actions">
                <button
                  className="primary-button"
                  disabled={busy === 'royalty' || !franchises.length}
                  type="submit"
                >
                  {busy === 'royalty' ? 'Saving…' : 'Record royalty'}
                </button>
              </div>
            </form>
          </section>

          <section className="data-panel finance-table-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">SETTLEMENT LEDGER</span>
                <h2>Royalty payments</h2>
              </div>
              <span className="result-count">{royalties.length} payments</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Franchise</th>
                    <th>Period</th>
                    <th>Amount</th>
                    <th>Reference</th>
                    <th>Recorded by</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {royalties.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.payment_date}</td>
                      <td>
                        <strong>{payment.branch_name}</strong>
                        <small className="muted-block">{payment.owner_name}</small>
                      </td>
                      <td>
                        {payment.period_from}
                        <small className="muted-block">to {payment.period_to}</small>
                      </td>
                      <td>{inr(payment.amount)}</td>
                      <td>{payment.reference ?? '—'}</td>
                      <td>{payment.recorded_by ?? '—'}</td>
                      <td>
                        <div className="row-actions">
                          <button onClick={() => openRoyaltyEditor(payment)} type="button">
                            Edit
                          </button>
                          <button
                            className="danger-action"
                            disabled={busy === `royalty-${payment.id}`}
                            onClick={() => void deleteRoyalty(payment)}
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
              {!royalties.length && (
                <div className="table-state">No royalty settlements recorded yet.</div>
              )}
            </div>
          </section>
        </>
      )}

      {editingProfile && (
        <div className="modal-backdrop" onClick={() => setEditingProfile(null)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog">
            <div className="modal-header">
              <div>
                <span className="eyebrow">EDIT FRANCHISE</span>
                <h2>{editingProfile.branch_name}</h2>
              </div>
              <button className="close-button" onClick={() => setEditingProfile(null)} type="button">
                ×
              </button>
            </div>
            <form onSubmit={(event) => void saveProfile(event)}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="edit-owner">Owner name</label>
                  <input
                    id="edit-owner"
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        owner_name: event.target.value,
                      }))
                    }
                    required
                    value={profileDraft.owner_name}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-phone">Owner phone</label>
                  <input
                    id="edit-phone"
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        owner_phone: event.target.value,
                      }))
                    }
                    value={profileDraft.owner_phone}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-email">Owner email</label>
                  <input
                    id="edit-email"
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        owner_email: event.target.value,
                      }))
                    }
                    type="email"
                    value={profileDraft.owner_email}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-status">Status</label>
                  <select
                    id="edit-status"
                    onChange={(event) =>
                      setProfileDraft((current) => ({ ...current, status: event.target.value }))
                    }
                    value={profileDraft.status}
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status.charAt(0).toUpperCase() + status.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="edit-start">Agreement start</label>
                  <input
                    id="edit-start"
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        agreement_start: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={profileDraft.agreement_start}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-end">Agreement end</label>
                  <input
                    id="edit-end"
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        agreement_end: event.target.value,
                      }))
                    }
                    type="date"
                    value={profileDraft.agreement_end}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-royalty">Royalty %</label>
                  <input
                    id="edit-royalty"
                    max={100}
                    min={0}
                    onChange={(event) =>
                      setProfileDraft((current) => ({
                        ...current,
                        royalty_percent: event.target.value,
                      }))
                    }
                    step="0.01"
                    type="number"
                    value={profileDraft.royalty_percent}
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="edit-notes">Notes</label>
                  <textarea
                    id="edit-notes"
                    onChange={(event) =>
                      setProfileDraft((current) => ({ ...current, notes: event.target.value }))
                    }
                    rows={2}
                    value={profileDraft.notes}
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  onClick={() => setEditingProfile(null)}
                  type="button"
                >
                  Cancel
                </button>
                <button
                  className="primary-button"
                  disabled={busy === `profile-${editingProfile.id}`}
                  type="submit"
                >
                  {busy === `profile-${editingProfile.id}` ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingRoyalty && (
        <div className="modal-backdrop" onClick={() => setEditingRoyalty(null)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog">
            <div className="modal-header">
              <div>
                <span className="eyebrow">EDIT ROYALTY</span>
                <h2>{editingRoyalty.branch_name}</h2>
              </div>
              <button className="close-button" onClick={() => setEditingRoyalty(null)} type="button">
                ×
              </button>
            </div>
            <form onSubmit={(event) => void saveRoyalty(event)}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="edit-royalty-amount">Amount (₹)</label>
                  <input
                    id="edit-royalty-amount"
                    min={0}
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({ ...current, amount: event.target.value }))
                    }
                    required
                    step="0.01"
                    type="number"
                    value={royaltyDraft.amount}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-royalty-date">Payment date</label>
                  <input
                    id="edit-royalty-date"
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({
                        ...current,
                        payment_date: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyDraft.payment_date}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-royalty-from">Period from</label>
                  <input
                    id="edit-royalty-from"
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({
                        ...current,
                        period_from: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyDraft.period_from}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-royalty-to">Period to</label>
                  <input
                    id="edit-royalty-to"
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({
                        ...current,
                        period_to: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={royaltyDraft.period_to}
                  />
                </div>
                <div className="field">
                  <label htmlFor="edit-royalty-reference">Reference</label>
                  <input
                    id="edit-royalty-reference"
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({
                        ...current,
                        reference: event.target.value,
                      }))
                    }
                    value={royaltyDraft.reference}
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="edit-royalty-notes">Notes</label>
                  <textarea
                    id="edit-royalty-notes"
                    onChange={(event) =>
                      setRoyaltyDraft((current) => ({ ...current, notes: event.target.value }))
                    }
                    rows={2}
                    value={royaltyDraft.notes}
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  onClick={() => setEditingRoyalty(null)}
                  type="button"
                >
                  Cancel
                </button>
                <button
                  className="primary-button"
                  disabled={busy === `royalty-${editingRoyalty.id}`}
                  type="submit"
                >
                  {busy === `royalty-${editingRoyalty.id}` ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default FranchisePage
