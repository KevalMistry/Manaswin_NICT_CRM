import { useCallback, useEffect, useState } from 'react'
import api from '../services/api'
import { todayInputValue } from '../utils/date'
import { getStoredUser } from '../utils/auth'
import { apiErrorMessage } from '../utils/apiErrors'
import { QRCodeSVG } from 'qrcode.react'

type Enrollment = { id: number; student_id: number; batch_id: number; status: string }
type Student = { id: number; full_name: string; student_code: string }
type Batch = { id: number; name: string; code: string }
type Attendance = { id: number; enrollment_id: number; attendance_date: string; status: string; remarks: string | null }
type AttendanceSession = { session_id: number; batch_id: number; attendance_date: string; expires_at: string; token: string }
type StaffPerson = {
  id: number
  full_name: string
  role_name: string
  branch_id: number | null
  branch_name: string | null
  phone: string | null
}
type StaffRecord = {
  id: number
  user_id: number
  attendance_date: string
  status: string
  check_in: string | null
  check_out: string | null
  remarks: string | null
  latitude: number | null
  longitude: number | null
  distance_meters: number | null
  location_status: string | null
  ip_address: string | null
  user_name: string | null
  user_role: string | null
  branch_name: string | null
}
type StaffSummary = {
  user_id: number
  user_name: string
  role_name: string
  branch_name: string | null
  present: number
  absent: number
  late: number
  leave: number
  half_day: number
  recorded_days: number
  attendance_rate: number
}

const STAFF_STATUSES = [
  { value: 'present', label: 'Present' },
  { value: 'absent', label: 'Absent' },
  { value: 'late', label: 'Late' },
  { value: 'leave', label: 'On leave' },
  { value: 'half_day', label: 'Half day' },
]

function currentMonthValue() {
  return todayInputValue().slice(0, 7)
}

function timeLabel(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function sessionDeadline(value: string) {
  return new Date(value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
}

function countdownLabel(seconds: number) {
  if (seconds <= 0) return 'Expired'
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}

function AttendancePage() {
  const currentUser = getStoredUser()
  const [tab, setTab] = useState<'students' | 'staff'>('students')
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [students, setStudents] = useState<Student[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [records, setRecords] = useState<Attendance[]>([])
  const [batchId, setBatchId] = useState('')
  const [date, setDate] = useState(todayInputValue())
  const [statusMap, setStatusMap] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [session, setSession] = useState<AttendanceSession | null>(null)
  const [sessionRemaining, setSessionRemaining] = useState(0)
  const [sessionMinutes, setSessionMinutes] = useState('10')

  const [staffPeople, setStaffPeople] = useState<StaffPerson[]>([])
  const [staffRecords, setStaffRecords] = useState<StaffRecord[]>([])
  const [staffStatusMap, setStaffStatusMap] = useState<Record<number, string>>({})
  const [staffLoading, setStaffLoading] = useState(false)
  const [staffSaving, setStaffSaving] = useState<number | null>(null)
  const [staffMessage, setStaffMessage] = useState('')
  const [month, setMonth] = useState(currentMonthValue())
  const [staffSummary, setStaffSummary] = useState<StaffSummary[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [enrollmentResponse, studentResponse, batchResponse, attendanceResponse] = await Promise.all([
        api.get<Enrollment[]>('/api/enrollments'),
        api.get<Student[]>('/api/students'),
        api.get<Batch[]>('/api/batches'),
        api.get<Attendance[]>('/api/attendance', { params: { attendance_date: date, batch_id: batchId || undefined } }),
      ])
      setEnrollments(enrollmentResponse.data)
      setStudents(studentResponse.data)
      setBatches(batchResponse.data)
      setRecords(attendanceResponse.data)
      setStatusMap(Object.fromEntries(attendanceResponse.data.map((record) => [record.enrollment_id, record.status])))
    } catch {
      setError('Unable to load attendance. Check your account access and API connection.')
    } finally {
      setLoading(false)
    }
  }, [batchId, date])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const loadStaff = useCallback(async () => {
    setStaffLoading(true)
    setError('')
    try {
      const [peopleResponse, recordResponse, summaryResponse] = await Promise.all([
        api.get<StaffPerson[]>('/api/attendance/staff/people'),
        api.get<StaffRecord[]>('/api/attendance/staff', { params: { attendance_date: date } }),
        api.get<StaffSummary[]>('/api/attendance/staff/summary', { params: { month } }),
      ])
      setStaffPeople(peopleResponse.data)
      setStaffRecords(recordResponse.data)
      setStaffSummary(summaryResponse.data)
      setStaffStatusMap(
        Object.fromEntries(recordResponse.data.map((record) => [record.user_id, record.status])),
      )
    } catch {
      setError('Unable to load faculty attendance. Check your account access and API connection.')
    } finally {
      setStaffLoading(false)
    }
  }, [date, month])

  useEffect(() => {
    if (tab !== 'staff') return
    const timer = window.setTimeout(() => void loadStaff(), 0)
    return () => window.clearTimeout(timer)
  }, [tab, loadStaff])

  useEffect(() => {
    if (!session) return
    const deadline = sessionDeadline(session.expires_at).getTime()
    const updateRemaining = () => {
      setSessionRemaining(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)))
    }
    const initialUpdate = window.setTimeout(updateRemaining, 0)
    const timer = window.setInterval(updateRemaining, 1000)
    return () => {
      window.clearTimeout(initialUpdate)
      window.clearInterval(timer)
    }
  }, [session])

  async function mark(enrollmentId: number) {
    setSaving(enrollmentId)
    setError('')
    try {
      await api.post('/api/attendance', { enrollment_id: enrollmentId, attendance_date: date, status: statusMap[enrollmentId] ?? 'present' })
      await load()
    } catch {
      setError('Unable to mark attendance. It may already be recorded for this date.')
    } finally {
      setSaving(null)
    }
  }

  async function updateAttendanceRecord(attendanceId: number, enrollmentId: number) {
    setSaving(enrollmentId)
    setError('')
    try {
      await api.patch(`/api/attendance/${attendanceId}`, {
        status: statusMap[enrollmentId] ?? 'present',
      })
      await load()
    } catch {
      setError('Unable to update attendance record.')
    } finally {
      setSaving(null)
    }
  }

  async function createSession() {
    if (!batchId) {
      setError('Select a batch before creating an attendance QR code.')
      return
    }
    try {
      const { data } = await api.post<AttendanceSession>('/api/attendance/sessions', {
        batch_id: Number(batchId),
        attendance_date: date,
        expires_in_minutes: Number(sessionMinutes),
      })
      setSession(data)
      setError('')
    } catch {
      setError('Unable to create the attendance QR code. Confirm that the batch is assigned to you.')
    }
  }

  async function saveStaff(userId: number) {
    setStaffSaving(userId)
    setError('')
    setStaffMessage('')
    try {
      await api.post<StaffRecord>('/api/attendance/staff', {
        user_id: userId,
        attendance_date: date,
        status: staffStatusMap[userId] ?? 'present',
      })
      setStaffMessage('Faculty attendance saved.')
      await loadStaff()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to save this attendance record.'))
    } finally {
      setStaffSaving(null)
    }
  }

  async function selfCheckIn() {
    setError('')
    setStaffMessage('')
    if (!navigator.geolocation) {
      setError('This browser cannot share your location. A location-verified check-in is required.')
      return
    }
    setStaffSaving(currentUser?.id ?? -1)
    setStaffMessage('Checking your location…')
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { data } = await api.post<StaffRecord>('/api/attendance/staff/check-in', {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy_meters: position.coords.accuracy,
          })
          setStaffMessage(
            data.distance_meters !== null
              ? `Checked in at ${data.branch_name ?? 'your branch'} (${Math.round(data.distance_meters)} m from the branch).`
              : 'Checked in for today.',
          )
          await loadStaff()
        } catch (requestError) {
          setError(
            apiErrorMessage(
              requestError,
              'Unable to check in. You may already be checked in, or you are outside the branch geofence.',
            ),
          )
        } finally {
          setStaffSaving(null)
        }
      },
      (geoError) => {
        setStaffSaving(null)
        setError(
          geoError.code === geoError.PERMISSION_DENIED
            ? 'Location permission is required for attendance. Allow location access and try again.'
            : 'Could not read your location. Move to an open area and try again.',
        )
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  }

  const studentName = (id: number) => students.find((student) => student.id === id)?.full_name ?? `Student #${id}`
  const studentCode = (id: number) => students.find((student) => student.id === id)?.student_code ?? '—'
  const filtered = enrollments.filter((enrollment) => enrollment.status === 'active' && (!batchId || enrollment.batch_id === Number(batchId)))
  const recorded = new Set(records.map((record) => record.enrollment_id))
  const staffRecorded = new Set(staffRecords.map((record) => record.user_id))
  const canMarkOthers = ['Super Admin', 'Branch Admin'].includes(currentUser?.role_name ?? '')
  const canSelfCheckIn = ['Faculty', 'Staff', 'Counsellor', 'Branch Admin'].includes(currentUser?.role_name ?? '')
  const ownRecord = staffRecords.find((record) => record.user_id === currentUser?.id)

  return <>
    <div className="page-heading module-heading">
      <div>
        <span className="eyebrow">ACADEMICS</span>
        <h1>Attendance</h1>
        <p>Mark and review daily attendance for students, faculty and staff.</p>
      </div>
    </div>

    <nav className="report-tabs" aria-label="Attendance type">
      <button
        type="button"
        className={tab === 'students' ? 'report-tab active' : 'report-tab'}
        onClick={() => setTab('students')}
      >
        Student attendance
      </button>
      <button
        type="button"
        className={tab === 'staff' ? 'report-tab active' : 'report-tab'}
        onClick={() => setTab('staff')}
      >
        Faculty &amp; staff attendance
      </button>
    </nav>

    {error && <div className="inline-error">{error}</div>}

    {tab === 'students' && (
      <>
        <section className="module-toolbar"><div className="toolbar-controls"><div className="field"><label htmlFor="attendance-date">Date</label><input id="attendance-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} /></div><div className="field"><label htmlFor="attendance-batch">Batch</label><select id="attendance-batch" value={batchId} onChange={(event) => setBatchId(event.target.value)}><option value="">All batches</option>{batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.name} ({batch.code})</option>)}</select></div><div className="field"><label htmlFor="qr-expiry">QR expires in</label><select id="qr-expiry" value={sessionMinutes} onChange={(event) => setSessionMinutes(event.target.value)}><option value="5">5 minutes</option><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option></select></div><button className="secondary-button" onClick={() => void createSession()} type="button">Generate attendance QR</button></div><span className="result-count">{filtered.length} active students · {recorded.size} marked</span></section>
        {session && <section className="data-panel qr-session-card"><div><span className="eyebrow">LIVE ATTENDANCE SESSION</span><h2>Scan this QR code</h2><p>{sessionRemaining > 0 ? `Students must scan it while logged in. It expires at ${sessionDeadline(session.expires_at).toLocaleTimeString()}.` : 'This attendance QR code has expired. Generate a new code to continue.'}</p><strong className="qr-countdown" aria-live="polite">{sessionRemaining > 0 ? `${countdownLabel(sessionRemaining)} remaining` : 'Expired'}</strong><code>{session.token}</code></div><QRCodeSVG value={`${window.location.origin}/student/portal?attendance_token=${encodeURIComponent(session.token)}`} size={180} includeMargin /></section>}
        <section className="data-panel">{loading ? <div className="table-state">Loading attendance…</div> : <div className="table-wrap"><table><thead><tr><th>Student</th><th>Batch</th><th>Status</th><th>Action</th></tr></thead><tbody>{filtered.map((enrollment) => { const existing = records.find((r) => r.enrollment_id === enrollment.id); return <tr key={enrollment.id}><td><div className="branch-name"><span className="branch-avatar">{studentName(enrollment.student_id).slice(0, 1).toUpperCase()}</span><span><strong>{studentName(enrollment.student_id)}</strong><small>{studentCode(enrollment.student_id)}</small></span></div></td><td>{batches.find((batch) => batch.id === enrollment.batch_id)?.name ?? `Batch #${enrollment.batch_id}`}</td><td><select value={statusMap[enrollment.id] ?? 'present'} onChange={(event) => setStatusMap({ ...statusMap, [enrollment.id]: event.target.value })}><option value="present">Present</option><option value="absent">Absent</option><option value="late">Late</option><option value="excused">Excused</option></select></td><td>{existing ? <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><span className="status-pill active-status"><i />Recorded</span><button className={statusMap[enrollment.id] !== existing.status ? 'primary-button' : 'secondary-button'} disabled={saving === enrollment.id} onClick={() => void updateAttendanceRecord(existing.id, enrollment.id)} type="button">{saving === enrollment.id ? 'Updating…' : 'Update'}</button></div> : <button className="primary-button" disabled={saving === enrollment.id} onClick={() => void mark(enrollment.id)} type="button">{saving === enrollment.id ? 'Saving…' : 'Mark attendance'}</button>}</td></tr> })}</tbody></table>{!filtered.length && <div className="table-state">No active enrollments found for this filter.</div>}</div>}</section>
      </>
    )}

    {tab === 'staff' && (
      <>
        <section className="module-toolbar">
          <div className="toolbar-controls">
            <div className="field">
              <label htmlFor="staff-date">Date</label>
              <input id="staff-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="staff-month">Summary month</label>
              <input id="staff-month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
            </div>
            {canSelfCheckIn && (
              <button
                className="secondary-button"
                disabled={staffSaving === (currentUser?.id ?? -1) || Boolean(ownRecord)}
                onClick={() => void selfCheckIn()}
                type="button"
              >
                {ownRecord ? 'Checked in today' : 'Self check-in'}
              </button>
            )}
          </div>
          <span className="result-count">
            {staffPeople.length} staff · {staffRecorded.size} marked
          </span>
        </section>

        {staffMessage && <div className="success-message">{staffMessage}</div>}

        <section className="data-panel">
          {staffLoading ? (
            <div className="table-state">Loading faculty attendance…</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Faculty / Staff</th>
                    <th>Role</th>
                    <th>Branch</th>
                    <th>Status</th>
                    <th>Check-in</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {staffPeople.map((person) => {
                    const record = staffRecords.find((item) => item.user_id === person.id)
                    return (
                      <tr key={person.id}>
                        <td>
                          <div className="branch-name">
                            <span className="branch-avatar">{person.full_name.slice(0, 1).toUpperCase()}</span>
                            <span>
                              <strong>{person.full_name}</strong>
                              <small>{person.phone || 'No phone on record'}</small>
                            </span>
                          </div>
                        </td>
                        <td>{person.role_name}</td>
                        <td>{person.branch_name ?? '—'}</td>
                        <td>
                          {person.id === currentUser?.id && !canMarkOthers ? (
                            <span className="status-pill">
                              <i />
                              {record
                                ? STAFF_STATUSES.find((status) => status.value === record.status)?.label ??
                                  record.status
                                : 'Not checked in'}
                            </span>
                          ) : (
                            <select
                              value={staffStatusMap[person.id] ?? 'present'}
                              onChange={(event) =>
                                setStaffStatusMap({ ...staffStatusMap, [person.id]: event.target.value })
                              }
                            >
                              {STAFF_STATUSES.map((status) => (
                                <option key={status.value} value={status.value}>
                                  {status.label}
                                </option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td>
                          {record ? timeLabel(record.check_in) : '—'}
                          {record?.location_status === 'verified' && (
                            <small className="muted-block">
                              Verified · {Math.round(record.distance_meters ?? 0)} m
                            </small>
                          )}
                        </td>
                        <td>
                          {record ? (
                            <span className="status-pill active-status">
                              <i />
                              {STAFF_STATUSES.find((status) => status.value === record.status)?.label ??
                                record.status}
                            </span>
                          ) : person.id === currentUser?.id ? (
                            <span className="muted">Use self check-in</span>
                          ) : canMarkOthers ? (
                            <button
                              className="primary-button"
                              disabled={staffSaving === person.id}
                              onClick={() => void saveStaff(person.id)}
                              type="button"
                            >
                              {staffSaving === person.id ? 'Saving…' : 'Save'}
                            </button>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {!staffPeople.length && (
                <div className="table-state">No faculty or staff records are available for your scope.</div>
              )}
            </div>
          )}
        </section>

        <section className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">MONTHLY SUMMARY</span>
              <h2>Attendance for {month}</h2>
            </div>
            <span className="result-count">{staffSummary.length} people</span>
          </div>
          {staffLoading ? (
            <div className="table-state">Loading summary…</div>
          ) : staffSummary.length === 0 ? (
            <div className="table-state">No faculty attendance recorded for this month.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Faculty / Staff</th>
                    <th>Role</th>
                    <th>Present</th>
                    <th>Absent</th>
                    <th>Late</th>
                    <th>Leave</th>
                    <th>Half day</th>
                    <th>Recorded</th>
                    <th>Attendance</th>
                  </tr>
                </thead>
                <tbody>
                  {staffSummary.map((row) => (
                    <tr key={row.user_id}>
                      <td>
                        <strong>{row.user_name}</strong>
                        <small>{row.branch_name ?? '—'}</small>
                      </td>
                      <td>{row.role_name}</td>
                      <td>{row.present}</td>
                      <td>{row.absent}</td>
                      <td>{row.late}</td>
                      <td>{row.leave}</td>
                      <td>{row.half_day}</td>
                      <td>{row.recorded_days}</td>
                      <td>
                        <span className={row.attendance_rate < 75 ? 'status-pill inactive-status' : 'status-pill active-status'}>
                          <i />
                          {row.attendance_rate}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </>
    )}
  </>
}

export default AttendancePage
