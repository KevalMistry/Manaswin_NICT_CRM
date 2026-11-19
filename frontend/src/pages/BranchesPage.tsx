import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import axios from 'axios'

type Branch = {
  id: number
  name: string
  code: string
  address: string | null
  phone: string | null
  email: string | null
  gstin: string | null
  latitude: number | string | null
  longitude: number | string | null
  geofence_radius_meters: number
  office_network: string | null
  is_active: boolean
  upi_id: string | null
  upi_payee_name: string | null
  upi_qr_code_url: string | null
  certificate_title: string | null
  marksheet_title: string | null
  certificate_primary_color: string
  certificate_accent_color: string
}

type BranchForm = {
  name: string
  code: string
  address: string
  phone: string
  email: string
  gstin: string
  upi_id: string
  upi_payee_name: string
  latitude: string
  longitude: string
  geofence_radius_meters: string
  office_network: string
  certificate_title: string
  marksheet_title: string
  certificate_primary_color: string
  certificate_accent_color: string
}

const emptyForm: BranchForm = {
  name: '',
  code: '',
  address: '',
  phone: '',
  email: '',
  gstin: '',
  upi_id: '',
  upi_payee_name: '',
  latitude: '',
  longitude: '',
  geofence_radius_meters: '150',
  office_network: '',
  certificate_title: '',
  marksheet_title: '',
  certificate_primary_color: '#172a43',
  certificate_accent_color: '#c19a3d',
}

function BranchesPage() {
  const [branches, setBranches] = useState<Branch[]>([])
  const [form, setForm] = useState<BranchForm>(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [paymentQrFile, setPaymentQrFile] = useState<File | null>(null)

  async function loadBranches() {
    setIsLoading(true)
    setError('')
    try {
      const { data } = await api.get<Branch[]>('/api/branches', { params: { include_inactive: true } })
      setBranches(data)
    } catch {
      setError('Could not load branches. Check that the API is running.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadBranches(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  function openCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setError('')
    setPaymentQrFile(null)
    setIsFormOpen(true)
  }

  function openEdit(branch: Branch) {
    setEditingId(branch.id)
    setForm({
      name: branch.name,
      code: branch.code,
      address: branch.address ?? '',
      phone: branch.phone ?? '',
      email: branch.email ?? '',
      gstin: branch.gstin ?? '',
      upi_id: branch.upi_id ?? '',
      upi_payee_name: branch.upi_payee_name ?? '',
      latitude: branch.latitude !== null ? String(branch.latitude) : '',
      longitude: branch.longitude !== null ? String(branch.longitude) : '',
      geofence_radius_meters: String(branch.geofence_radius_meters ?? 150),
      office_network: branch.office_network ?? '',
      certificate_title: branch.certificate_title ?? '',
      marksheet_title: branch.marksheet_title ?? '',
      certificate_primary_color: branch.certificate_primary_color ?? '#172a43',
      certificate_accent_color: branch.certificate_accent_color ?? '#c19a3d',
    })
    setError('')
    setPaymentQrFile(null)
    setIsFormOpen(true)
  }

  function updateField(field: keyof BranchForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError('This browser does not support location capture. Enter the coordinates manually.')
      return
    }
    setError('')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setForm((current) => ({
          ...current,
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6),
        }))
      },
      () => {
        setError('Location permission was denied. Allow location access or enter the coordinates manually.')
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    const payload = {
      name: form.name,
      code: form.code,
      address: form.address || null,
      phone: form.phone || null,
      email: form.email || null,
      gstin: form.gstin || null,
      upi_id: form.upi_id || null,
      upi_payee_name: form.upi_payee_name || null,
      latitude: form.latitude ? Number(form.latitude) : null,
      longitude: form.longitude ? Number(form.longitude) : null,
      geofence_radius_meters: Number(form.geofence_radius_meters || 150),
      office_network: form.office_network || null,
      certificate_title: form.certificate_title || null,
      marksheet_title: form.marksheet_title || null,
      certificate_primary_color: form.certificate_primary_color,
      certificate_accent_color: form.certificate_accent_color,
    }
    try {
      if (editingId) {
        await api.patch(`/api/branches/${editingId}`, payload)
        if (paymentQrFile) {
          const formData = new FormData()
          formData.append('file', paymentQrFile)
          await api.post(`/api/branches/${editingId}/payment-qr`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        }
      } else {
        await api.post('/api/branches', payload)
      }
      setIsFormOpen(false)
      await loadBranches()
    } catch (requestError) {
      const detail = requestError instanceof Error ? requestError.message : ''
      setError(axios.isAxiosError(requestError) && requestError.response?.status === 403 ? 'You do not have permission to manage branches.' : detail || 'Unable to save this branch.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deactivate(branch: Branch) {
    if (!window.confirm(`Deactivate ${branch.name}?`)) return
    setError('')
    try {
      await api.delete(`/api/branches/${branch.id}`)
      await loadBranches()
    } catch (requestError) {
      const detail = requestError instanceof Error ? requestError.message : ''
      setError(axios.isAxiosError(requestError) && requestError.response?.status === 403 ? 'You do not have permission to manage branches.' : detail || 'Unable to deactivate this branch.')
    }
  }

  const filteredBranches = branches.filter((branch) =>
    `${branch.name} ${branch.code} ${branch.address ?? ''}`.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">ORGANIZATION</span>
          <h1>Branches</h1>
          <p>Manage your institute locations and branch operations.</p>
        </div>
        <button className="primary-button" onClick={openCreate} type="button">+ Add branch</button>
      </div>
      {error && <div className="inline-error">{error}</div>}
      <section className="module-toolbar">
        <div className="search-box"><span>⌕</span><input aria-label="Search branches" placeholder="Search branches…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <span className="result-count">{filteredBranches.length} {filteredBranches.length === 1 ? 'branch' : 'branches'}</span>
      </section>
      <section className="data-panel">
        {isLoading ? (
          <div className="table-state">Loading branches…</div>
        ) : filteredBranches.length === 0 ? (
          <div className="table-state"><div className="empty-icon">◫</div><strong>{search ? 'No matching branches' : 'No branches yet'}</strong><p>{search ? 'Try a different search term.' : 'Add your first branch to start organizing the institute.'}</p>{!search && <button className="primary-button" onClick={openCreate} type="button">Add your first branch</button>}</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Branch</th><th>Code</th><th>Contact</th><th>Status</th><th /></tr></thead>
              <tbody>{filteredBranches.map((branch) => <tr key={branch.id}>
                <td><div className="branch-name"><span className="branch-avatar">{branch.name.slice(0, 1).toUpperCase()}</span><span><strong>{branch.name}</strong><small>{branch.address || 'No address added'}</small></span></div></td>
                <td><span className="code-pill">{branch.code}</span></td>
                <td><span className="contact-cell">{branch.email || branch.phone || '—'}</span></td>
                <td><span className={branch.is_active ? 'status-pill active-status' : 'status-pill inactive-status'}><i />{branch.is_active ? 'Active' : 'Inactive'}</span></td>
                <td><div className="row-actions"><button onClick={() => openEdit(branch)} type="button">Edit</button>{branch.is_active && <button className="danger-action" onClick={() => void deactivate(branch)} type="button">Deactivate</button>}</div></td>
              </tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
      {isFormOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsFormOpen(false) }}>
        <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="branch-modal-title">
          <div className="modal-header"><div><span className="eyebrow">{editingId ? 'EDIT BRANCH' : 'NEW BRANCH'}</span><h2 id="branch-modal-title">{editingId ? 'Update branch' : 'Add a branch'}</h2></div><button className="close-button" onClick={() => setIsFormOpen(false)} type="button">×</button></div>
          <form onSubmit={submit}>
            <div className="form-grid"><div className="field"><label htmlFor="branch-name">Branch name</label><input id="branch-name" value={form.name} onChange={(event) => updateField('name', event.target.value)} placeholder="e.g. NICT Main Center" required /></div><div className="field"><label htmlFor="branch-code">Branch code</label><input id="branch-code" value={form.code} onChange={(event) => updateField('code', event.target.value.toUpperCase())} placeholder="e.g. MAIN-01" required /></div><div className="field full-field"><label htmlFor="branch-address">Address</label><input id="branch-address" value={form.address} onChange={(event) => updateField('address', event.target.value)} placeholder="Branch address" /></div><div className="field"><label htmlFor="branch-phone">Phone</label><input id="branch-phone" value={form.phone} onChange={(event) => updateField('phone', event.target.value)} placeholder="+91…" /></div><div className="field"><label htmlFor="branch-email">Email</label><input id="branch-email" type="email" value={form.email} onChange={(event) => updateField('email', event.target.value)} placeholder="branch@institute.com" /></div>            <div className="field"><label htmlFor="branch-gstin">GSTIN (for invoices)</label><input id="branch-gstin" value={form.gstin} onChange={(event) => updateField('gstin', event.target.value.toUpperCase())} placeholder="e.g. 24ABCDE1234F1Z5" maxLength={20} /><small className="field-hint">Printed on admission payment invoices.</small></div>            <div className="field full-field"><small className="field-hint">Certificate and marksheet formats are managed from the Certificates page, where you can use the guided editor or safe HTML templates.</small></div><div className="field"><label htmlFor="branch-upi-id">Institution UPI ID</label><input id="branch-upi-id" value={form.upi_id} onChange={(event) => updateField('upi_id', event.target.value.trim())} placeholder="e.g. institute@upi" maxLength={120} /></div><div className="field"><label htmlFor="branch-upi-payee">UPI payee name</label><input id="branch-upi-payee" value={form.upi_payee_name} onChange={(event) => updateField('upi_payee_name', event.target.value)} placeholder="e.g. NICT Institute" maxLength={120} /></div><div className="field full-field"><label htmlFor="branch-payment-qr">Institution UPI QR code</label><input id="branch-payment-qr" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setPaymentQrFile(event.target.files?.[0] ?? null)} disabled={!editingId} /><small className="field-hint">{editingId ? 'Only the Super Admin can replace this branch payment QR code.' : 'Create the branch first, then upload its payment QR code.'}</small></div><div className="field"><label htmlFor="branch-latitude">Check-in latitude</label><input id="branch-latitude" type="number" step="0.000001" min="-90" max="90" value={form.latitude} onChange={(event) => updateField('latitude', event.target.value)} placeholder="e.g. 20.389200" /></div><div className="field"><label htmlFor="branch-longitude">Check-in longitude</label><input id="branch-longitude" type="number" step="0.000001" min="-180" max="180" value={form.longitude} onChange={(event) => updateField('longitude', event.target.value)} placeholder="e.g. 72.910600" /></div><div className="field"><label htmlFor="branch-radius">Geofence radius (metres)</label><input id="branch-radius" type="number" min="25" max="5000" value={form.geofence_radius_meters} onChange={(event) => updateField('geofence_radius_meters', event.target.value)} /><small className="field-hint">Staff can self check-in only inside this distance.</small></div><div className="field"><label htmlFor="branch-network">Office network (optional)</label><input id="branch-network" value={form.office_network} onChange={(event) => updateField('office_network', event.target.value)} placeholder="e.g. 203.0.113.0/24, 198.51.100.7" /><small className="field-hint">Comma-separated IPs or CIDR ranges. Leave blank to skip the network check.</small></div><div className="field full-field"><button className="secondary-button" onClick={useCurrentLocation} type="button">📍 Use my current location</button><small className="field-hint">Stand at the branch entrance when capturing coordinates.</small></div></div>
            <div className="modal-actions"><button className="secondary-button" onClick={() => setIsFormOpen(false)} type="button">Cancel</button><button className="primary-button" disabled={isSaving} type="submit">{isSaving ? 'Saving…' : editingId ? 'Save changes' : 'Create branch'}</button></div>
          </form>
        </div>
      </div>}
    </>
  )
}

export default BranchesPage
