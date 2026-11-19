import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import api from '../services/api'
import { ChartGrid } from '../components/Charts'
import type {
  DashboardSummary,
  SuperAdminDashboardData,
  BranchAdminDashboardData,
  FacultyDashboardData,
  StaffDashboardData,
  CounsellorDashboardData,
} from '../types'
import { todayInputValue } from '../utils/date'

type Health = { status: string; database: string }

function DashboardPage() {
  const navigate = useNavigate()
  const [health, setHealth] = useState<Health | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<Health>('/api/health').catch(() => ({ data: null })),
      api.get<DashboardSummary>('/api/dashboard/summary').catch(() => ({ data: null })),
    ]).then(([healthResp, summaryResp]) => {
      if (healthResp.data) setHealth(healthResp.data)
      if (summaryResp.data) setSummary(summaryResp.data)
      setLoading(false)
    })
  }, [])

  const currentUser = JSON.parse(localStorage.getItem('current_user') ?? '{}') as {
    full_name?: string
    role_name?: string
    role_id?: number
  }
  const roleName =
    summary?.role_name ??
    currentUser.role_name ??
    (currentUser.role_id === 1 ? 'Super Admin' : currentUser.role_id === 2 ? 'Branch Admin' : 'Staff')

  const userName = currentUser.full_name ?? 'Administrator'
  const firstName = userName.split(' ')[0]
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  if (loading) {
    return <div className="table-state">Loading your personalized dashboard…</div>
  }

  const roleDashboard = summary?.role_dashboard

  return (
    <div className="personalized-dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            {roleName.toUpperCase()} ·{' '}
            {new Date()
              .toLocaleDateString('en-IN', {
                weekday: 'long',
                month: 'long',
                day: 'numeric',
                year: 'numeric',
              })
              .toUpperCase()}
          </span>
          <h1>
            {greeting}, {firstName} <span className="wave">✦</span>
          </h1>
          <p>
            {roleName === 'Super Admin'
              ? 'Complete multi-branch oversight and performance intelligence across all institute locations.'
              : roleName === 'Branch Admin'
              ? 'Real-time operational command center for your assigned branch.'
              : roleName === 'Faculty'
              ? 'Teaching dashboard, live attendance, and academic examination progress.'
              : roleName === 'Staff'
              ? 'Daily front-desk operations, fee collection tracking, and assigned responsibilities.'
              : roleName === 'Counsellor'
              ? 'Student admissions, counselling watchlist, and student follow-up tracker.'
              : 'Here is what is happening across your workspace today.'}
          </p>
        </div>
      </div>

      <div className="system-status">
        <span className={health?.database === 'connected' ? 'status-dot online' : 'status-dot'} />
        <strong>System operational</strong>
        <span className="status-divider" />
        <span>API {health?.status === 'healthy' ? 'connected' : 'checking…'}</span>
        <span className="status-divider" />
        <span>Database {health?.database ?? 'connected'}</span>
        <span className="status-divider" />
        <span className="status-role-badge">{roleName} Portal</span>
      </div>

      {/* Render dedicated personalized views */}
      {roleDashboard?.dashboard_type === 'super_admin' && (
        <SuperAdminView data={roleDashboard as SuperAdminDashboardData} navigate={navigate} />
      )}

      {roleDashboard?.dashboard_type === 'branch_admin' && (
        <BranchAdminView data={roleDashboard as BranchAdminDashboardData} navigate={navigate} />
      )}

      {roleDashboard?.dashboard_type === 'faculty' && (
        <FacultyView data={roleDashboard as FacultyDashboardData} navigate={navigate} />
      )}

      {roleDashboard?.dashboard_type === 'staff' && (
        <StaffView data={roleDashboard as StaffDashboardData} navigate={navigate} />
      )}

      {roleDashboard?.dashboard_type === 'counsellor' && (
        <CounsellorView data={roleDashboard as CounsellorDashboardData} navigate={navigate} />
      )}

      {(!roleDashboard || roleDashboard.dashboard_type === 'default') && (
        <DefaultFallbackView summary={summary} navigate={navigate} />
      )}
    </div>
  )
}

// -------------------------------------------------------------
// 1. SUPER ADMIN VIEW
// -------------------------------------------------------------
function SuperAdminView({
  data,
  navigate,
}: {
  data: SuperAdminDashboardData
  navigate: (path: string) => void
}) {
  return (
    <>
      <section className="metric-grid super-admin-metrics">
        <article className="metric-card">
          <div className="metric-icon blue">◫</div>
          <div className="metric-label">Total Branches</div>
          <div className="metric-value">{data.total_branches}</div>
          <div className="metric-detail">{data.active_branches} active locations</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon violet">♙</div>
          <div className="metric-label">Total Students</div>
          <div className="metric-value">{data.total_students}</div>
          <div className="metric-detail">Across all branches</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon green">₹</div>
          <div className="metric-label">Monthly Revenue</div>
          <div className="metric-value">₹{data.monthly_revenue.toLocaleString('en-IN')}</div>
          <div className="metric-detail">All-time ₹{data.total_revenue.toLocaleString('en-IN')}</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">✓</div>
          <div className="metric-label">Institute Attendance</div>
          <div className="metric-value">{data.overall_attendance_rate}%</div>
          <div className="metric-detail">Present or late</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon teal">♟</div>
          <div className="metric-label">Team Members</div>
          <div className="metric-value">{data.total_faculty + data.total_staff}</div>
          <div className="metric-detail">
            {data.total_faculty} Faculty · {data.total_staff} Admins &amp; Staff
          </div>
        </article>
      </section>

      <section className="dashboard-grid super-admin-grid">
        <article className="data-panel branch-comparison-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">HEAD OFFICE CENTRAL CONTROL</span>
              <h2>Multi-Branch Overview</h2>
            </div>
            <button className="secondary-button btn-sm" onClick={() => navigate('/branches')} type="button">
              + Manage Branches
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>Branch Admin</th>
                  <th>Students</th>
                  <th>Batches</th>
                  <th>Monthly Revenue</th>
                  <th>Attendance</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.branches.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <div className="branch-name">
                        <span className="branch-avatar">{b.name.slice(0, 1).toUpperCase()}</span>
                        <span>
                          <strong>{b.name}</strong>
                          <small>
                            <span className="code-pill">{b.code}</span> {b.address || ''}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>{b.admin_name}</td>
                    <td>
                      <strong>{b.students_count}</strong>
                    </td>
                    <td>{b.batches_count}</td>
                    <td>
                      <strong>₹{b.monthly_revenue.toLocaleString('en-IN')}</strong>
                    </td>
                    <td>{b.attendance_rate}%</td>
                    <td>
                      <span
                        className={b.is_active ? 'status-pill active-status' : 'status-pill inactive-status'}
                      >
                        <i />
                        {b.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="data-panel audit-stream-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">SYSTEM SECURITY AUDIT</span>
              <h2>Live Activity Stream</h2>
            </div>
            <span className="result-count">Real-time</span>
          </div>

          <div className="audit-list">
            {data.recent_activities.length === 0 ? (
              <div className="table-state">No audit events logged yet.</div>
            ) : (
              data.recent_activities.map((log) => (
                <div key={log.id} className="audit-item">
                  <div className="audit-icon">⦿</div>
                  <div className="audit-content">
                    <div className="audit-title">
                      <strong>{log.actor_name}</strong> {log.action}
                    </div>
                    <div className="audit-sub">
                      Target: {log.resource_type} {log.resource_id ? `#${log.resource_id}` : ''} ·{' '}
                      {new Date(log.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </article>
      </section>

      <ChartGrid
        data={data.charts}
        titles={{
          revenue_trend: 'Monthly Revenue',
          admissions_trend: 'Admissions Trend',
          branch_revenue: 'Branch Revenue',
          course_popularity: 'Course Popularity',
          fee_aging: 'Outstanding Fee Aging',
        }}
      />

      <section className="quick-actions-bar">
        <h3>Administrative Shortcuts:</h3>
        <button className="primary-button btn-sm" onClick={() => navigate('/branches')} type="button">
          + Add Branch
        </button>
        <button className="secondary-button btn-sm" onClick={() => navigate('/staff')} type="button">
          + Add Account
        </button>
        <button className="secondary-button btn-sm" onClick={() => navigate('/permissions')} type="button">
          ⚿ Manage Role Permissions
        </button>
        <button className="secondary-button btn-sm" onClick={() => navigate('/courses')} type="button">
          ▦ Course Catalog
        </button>
      </section>
    </>
  )
}

// -------------------------------------------------------------
// 2. BRANCH ADMIN VIEW
// -------------------------------------------------------------
function BranchAdminView({
  data,
  navigate,
}: {
  data: BranchAdminDashboardData
  navigate: (path: string) => void
}) {
  return (
    <>
      <div className="branch-hero-banner">
        <div>
          <span className="eyebrow">BRANCH OPERATIONS HUB</span>
          <h2>{data.branch_name}</h2>
          <p>
            Branch Code: <span className="code-pill">{data.branch_code}</span> · Active command center
          </p>
        </div>
        <div className="branch-hero-actions">
          <button className="primary-button" onClick={() => navigate('/enrollments')} type="button">
            + New Admission
          </button>
          <button className="secondary-button" onClick={() => navigate('/permissions')} type="button">
            ⚿ Branch Permissions
          </button>
        </div>
      </div>

      <section className="metric-grid branch-metrics">
        <article className="metric-card">
          <div className="metric-icon blue">♙</div>
          <div className="metric-label">Branch Students</div>
          <div className="metric-value">{data.branch_students_count}</div>
          <div className="metric-detail">Active student profiles</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon violet">▦</div>
          <div className="metric-label">Active Batches</div>
          <div className="metric-value">{data.branch_batches_count}</div>
          <div className="metric-detail">Ongoing training groups</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon green">₹</div>
          <div className="metric-label">Monthly Collections</div>
          <div className="metric-value">₹{data.monthly_collection.toLocaleString('en-IN')}</div>
          <div className="metric-detail">Received this month</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">⚠</div>
          <div className="metric-label">Pending Fees</div>
          <div className="metric-value">₹{data.outstanding_balance.toLocaleString('en-IN')}</div>
          <div className="metric-detail">Total branch balance</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon teal">✓</div>
          <div className="metric-label">Branch Attendance</div>
          <div className="metric-value">{data.branch_attendance_rate}%</div>
          <div className="metric-detail">
            {data.branch_faculty_count} Faculty · {data.branch_staff_count} Staff
          </div>
        </article>

        <article className="metric-card">
          <div className="metric-icon blue">♟</div>
          <div className="metric-label">Staff Present Today</div>
          <div className="metric-value">{data.staff_attendance_today.present_today}</div>
          <div className="metric-detail">
            {data.staff_attendance_today.on_leave_today} on leave ·{' '}
            {data.staff_attendance_today.recorded_today} recorded
          </div>
        </article>
      </section>

      <ChartGrid
        data={data.charts}
        titles={{
          revenue_trend: 'Monthly Collection',
          admissions_trend: 'Admissions Trend',
          attendance_trend: 'Attendance Trend',
          course_popularity: 'Course Popularity',
          fee_aging: 'Outstanding Fee Aging',
        }}
      />

      <section className="dashboard-grid">
        <article className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">BATCH HEALTH</span>
              <h2>Active Training Batches</h2>
            </div>
            <button className="secondary-button btn-sm" onClick={() => navigate('/courses')} type="button">
              + Add Batch
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>Course</th>
                  <th>Assigned Faculty</th>
                  <th>Capacity</th>
                  <th>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {data.batches.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="table-state">
                      No active batches found in this branch.
                    </td>
                  </tr>
                ) : (
                  data.batches.map((batch) => {
                    const fillPercent = Math.min(
                      100,
                      Math.round((batch.enrolled_count / (batch.capacity || 1)) * 100)
                    )
                    return (
                      <tr key={batch.id}>
                        <td>
                          <strong>{batch.name}</strong>
                          <small className="muted-block">{batch.code}</small>
                        </td>
                        <td>{batch.course_name}</td>
                        <td>{batch.faculty_name}</td>
                        <td>
                          <div className="capacity-bar-wrap">
                            <span className="capacity-text">
                              {batch.enrolled_count} / {batch.capacity}
                            </span>
                            <div className="capacity-track">
                              <div className="capacity-fill" style={{ width: `${fillPercent}%` }} />
                            </div>
                          </div>
                        </td>
                        <td>
                          <small>{batch.start_date}</small>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">OVERDUE ACCOUNTS</span>
              <h2>Outstanding Fee Alerts</h2>
            </div>
            <button className="secondary-button btn-sm" onClick={() => navigate('/fees')} type="button">
              Fee Register →
            </button>
          </div>

          <div className="overdue-list">
            {data.overdue_installments.length === 0 ? (
              <div className="table-state">All student installment accounts are up to date! 🎉</div>
            ) : (
              data.overdue_installments.map((inst) => (
                <div key={inst.installment_id} className="overdue-item">
                  <div className="overdue-info">
                    <strong>{inst.student_name}</strong>
                    <span>
                      {inst.enrollment_code} · Phone: {inst.student_phone}
                    </span>
                  </div>
                  <div className="overdue-val">
                    <span className="danger-amount">₹{inst.amount.toLocaleString('en-IN')}</span>
                    <small>Due: {inst.due_date}</small>
                  </div>
                </div>
              ))
            )}
          </div>
        </article>
      </section>
    </>
  )
}

// -------------------------------------------------------------
// 3. FACULTY VIEW
// -------------------------------------------------------------
function FacultyView({
  data,
  navigate,
}: {
  data: FacultyDashboardData
  navigate: (path: string) => void
}) {
  const [activeQrModal, setActiveQrModal] = useState<{
    batchId: number
    batchName: string
    token: string
    expiresAt: string
  } | null>(null)
  const [generatingQr, setGeneratingQr] = useState<number | null>(null)
  const [error, setError] = useState('')

  async function generateInstantQr(batchId: number, batchName: string) {
    setGeneratingQr(batchId)
    setError('')
    try {
      const todayStr = todayInputValue()
      const { data: session } = await api.post<{
        session_id: number
        batch_id: number
        attendance_date: string
        expires_at: string
        token: string
      }>('/api/attendance/sessions', {
        batch_id: batchId,
        attendance_date: todayStr,
        expires_in_minutes: 15,
      })
      setActiveQrModal({
        batchId,
        batchName,
        token: session.token,
        expiresAt: session.expires_at,
      })
    } catch {
      setError('Unable to create instant QR code. Please check batch assignment.')
    } finally {
      setGeneratingQr(null)
    }
  }

  return (
    <>
      {error && <div className="inline-error">{error}</div>}

      <section className="metric-grid faculty-metrics">
        <article className="metric-card">
          <div className="metric-icon blue">▦</div>
          <div className="metric-label">My Assigned Batches</div>
          <div className="metric-value">{data.assigned_batches_count}</div>
          <div className="metric-detail">Active training groups</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon violet">♙</div>
          <div className="metric-label">My Students</div>
          <div className="metric-value">{data.total_my_students}</div>
          <div className="metric-detail">Under your instruction</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon green">✓</div>
          <div className="metric-label">Today’s Attendance</div>
          <div className="metric-value">
            {data.attendance_marked_today_count} / {data.batches_today_count}
          </div>
          <div className="metric-detail">Batches marked today</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">▤</div>
          <div className="metric-label">Class Attendance Rate</div>
          <div className="metric-value">{data.attendance_rate}%</div>
          <div className="metric-detail">Across all your classes</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon teal">✓</div>
          <div className="metric-label">My Attendance</div>
          <div className="metric-value">{data.my_attendance.attendance_rate}%</div>
          <div className="metric-detail">
            {data.my_attendance.recorded_days} days recorded this month
          </div>
        </article>
      </section>

      <ChartGrid
        data={data.charts}
        titles={{
          attendance_trend: 'Attendance Trend',
          exam_grades: 'Grade Distribution',
          batch_students: 'Students per Batch',
        }}
      />

      <section className="data-panel faculty-batches-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">TEACHING SCHEDULE &amp; CLASSES</span>
            <h2>My Assigned Classes</h2>
          </div>
          <span className="result-count">{data.my_batches.length} batches</span>
        </div>

        <div className="faculty-batch-cards">
          {data.my_batches.length === 0 ? (
            <div className="table-state">No batches are currently assigned to your faculty profile.</div>
          ) : (
            data.my_batches.map((batch) => (
              <div key={batch.id} className="faculty-batch-card">
                <div className="faculty-batch-header">
                  <div>
                    <span className="code-pill">{batch.code}</span>
                    <h3>{batch.name}</h3>
                    <p className="course-subtitle">{batch.course_name}</p>
                  </div>
                  <span
                    className={
                      batch.attendance_marked_today
                        ? 'status-pill active-status'
                        : 'status-pill pending-status'
                    }
                  >
                    <i />
                    {batch.attendance_marked_today ? 'Attendance Done' : 'Attendance Pending'}
                  </span>
                </div>

                <div className="faculty-batch-meta">
                  <span>
                    👥 <strong>{batch.students_count}</strong> students enrolled (Capacity: {batch.capacity})
                  </span>
                  <span>📅 Started: {batch.start_date}</span>
                </div>

                <div className="faculty-batch-actions">
                  <button
                    className="primary-button btn-sm"
                    disabled={generatingQr === batch.id}
                    onClick={() => void generateInstantQr(batch.id, batch.name)}
                    type="button"
                  >
                    {generatingQr === batch.id ? 'Generating…' : '⚡ Live Attendance QR'}
                  </button>
                  <button
                    className="secondary-button btn-sm"
                    onClick={() => navigate('/attendance')}
                    type="button"
                  >
                    Mark Manually
                  </button>
                  <button
                    className="secondary-button btn-sm"
                    onClick={() => navigate('/examinations')}
                    type="button"
                  >
                    Enter Exam Marks
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">ACADEMIC EXAMINATIONS</span>
            <h2>Recent Examinations</h2>
          </div>
          <button className="secondary-button btn-sm" onClick={() => navigate('/examinations')} type="button">
            View All Exams →
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Exam Name</th>
                <th>Batch</th>
                <th>Exam Date</th>
                <th>Subjects</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_exams.length === 0 ? (
                <tr>
                  <td colSpan={5} className="table-state">
                    No examinations recorded for your classes yet.
                  </td>
                </tr>
              ) : (
                data.recent_exams.map((ex) => (
                  <tr key={ex.id}>
                    <td>
                      <strong>{ex.name}</strong>
                    </td>
                    <td>{ex.batch_name}</td>
                    <td>{ex.exam_date}</td>
                    <td>{ex.subjects_count} subjects</td>
                    <td>
                      <span
                        className={ex.is_published ? 'status-pill active-status' : 'status-pill inactive-status'}
                      >
                        <i />
                        {ex.is_published ? 'Published' : 'Draft'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Live QR Modal */}
      {activeQrModal && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card qr-live-modal" role="dialog" aria-modal="true">
            <div className="modal-header">
              <div>
                <span className="eyebrow">LIVE QR ATTENDANCE · {activeQrModal.batchName}</span>
                <h2>Scan for Today’s Attendance</h2>
              </div>
              <button className="close-button" onClick={() => setActiveQrModal(null)} type="button">
                ×
              </button>
            </div>

            <div className="qr-live-body">
              <QRCodeSVG
                value={`${window.location.origin}/student/portal?attendance_token=${encodeURIComponent(
                  activeQrModal.token
                )}`}
                size={220}
                includeMargin
              />
              <div className="qr-instructions">
                <p>
                  <strong>Students:</strong> Point your smartphone camera or open the Student Portal to mark
                  attendance instantly.
                </p>
                <div className="qr-expiry-tag">
                  Valid until: {new Date(activeQrModal.expiresAt).toLocaleTimeString()}
                </div>
                <div className="token-copy-box">
                  <code>{activeQrModal.token}</code>
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => {
                  void navigator.clipboard.writeText(activeQrModal.token).then(() => {
                    setError('Attendance token copied to clipboard.')
                  }).catch(() => {
                    setError('Unable to copy the token. Select it manually.')
                  })
                }}
                type="button"
              >
                Copy Token
              </button>
              <button
                className="primary-button"
                onClick={() => setActiveQrModal(null)}
                type="button"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// -------------------------------------------------------------
// 4. STAFF VIEW
// -------------------------------------------------------------
function StaffView({
  data,
  navigate,
}: {
  data: StaffDashboardData
  navigate: (path: string) => void
}) {
  return (
    <>
      <section className="metric-grid staff-metrics">
        <article className="metric-card">
          <div className="metric-icon green">₹</div>
          <div className="metric-label">Today’s Collections</div>
          <div className="metric-value">₹{data.today_collection.toLocaleString('en-IN')}</div>
          <div className="metric-detail">Monthly: ₹{data.monthly_collection.toLocaleString('en-IN')}</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">⏰</div>
          <div className="metric-label">Overdue Installments</div>
          <div className="metric-value">{data.pending_installments_count}</div>
          <div className="metric-detail">
            Totaling ₹{data.total_pending_amount.toLocaleString('en-IN')}
          </div>
        </article>

        <article className="metric-card">
          <div className="metric-icon blue">↗</div>
          <div className="metric-label">Active Enrollments</div>
          <div className="metric-value">{data.active_enrollments_count}</div>
          <div className="metric-detail">Operational students</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon violet">♟</div>
          <div className="metric-label">My Responsibilities</div>
          <div className="metric-value">{data.my_pending_responsibilities_count}</div>
          <div className="metric-detail">Pending task items</div>
        </article>
      </section>

      <ChartGrid
        data={data.charts}
        titles={{
          collection_trend: 'Collection Trend',
          payment_methods: 'Payment Methods',
          fee_aging: 'Outstanding Fee Aging',
          admissions_trend: 'Admissions Trend',
        }}
      />

      <section className="dashboard-grid">
        <article className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">CASH &amp; BANK OPERATIONS</span>
              <h2>Recent Payment Receipts</h2>
            </div>
            <button className="primary-button btn-sm" onClick={() => navigate('/fees')} type="button">
              + Record Payment
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Receipt #</th>
                  <th>Student</th>
                  <th>Amount</th>
                  <th>Method</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_payments.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="table-state">
                      No payments recorded recently.
                    </td>
                  </tr>
                ) : (
                  data.recent_payments.map((p) => (
                    <tr key={p.receipt_number}>
                      <td>
                        <span className="code-pill">{p.receipt_number}</span>
                      </td>
                      <td>
                        <strong>{p.student_name}</strong>
                      </td>
                      <td>₹{p.amount.toLocaleString('en-IN')}</td>
                      <td>{p.payment_method}</td>
                      <td>{p.payment_date}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">MY TASK CHECKLIST</span>
              <h2>Assigned Responsibilities</h2>
            </div>
            <span className="result-count">{data.my_responsibilities.length} items</span>
          </div>

          <div className="task-list">
            {data.my_responsibilities.length === 0 ? (
              <div className="table-state">No tasks assigned to your desk today. 👍</div>
            ) : (
              data.my_responsibilities.map((r) => (
                <div key={r.id} className="task-item">
                  <div>
                    <strong>{r.title}</strong>
                    <div className="task-sub">
                      Dept: {r.department} · Due: {r.due_date || 'No deadline'}
                    </div>
                  </div>
                  <span className={`status-pill ${r.status === 'completed' ? 'active-status' : 'pending-status'}`}>
                    <i />
                    {r.status.replace('_', ' ')}
                  </span>
                </div>
              ))
            )}
          </div>
        </article>
      </section>
    </>
  )
}

// -------------------------------------------------------------
// 5. COUNSELLOR VIEW
// -------------------------------------------------------------
function CounsellorView({
  data,
  navigate,
}: {
  data: CounsellorDashboardData
  navigate: (path: string) => void
}) {
  const [followUpMessage, setFollowUpMessage] = useState('')

  return (
    <>
      {followUpMessage && <div className="success-message dashboard-feedback">{followUpMessage}</div>}
      <section className="metric-grid counsellor-metrics">
        <article className="metric-card">
          <div className="metric-icon violet">☎</div>
          <div className="metric-label">Open Enquiries</div>
          <div className="metric-value">{data.open_enquiries_count}</div>
          <div className="metric-detail">Leads in the pipeline</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">◷</div>
          <div className="metric-label">Follow-ups Due</div>
          <div className="metric-value">{data.followups_due_count}</div>
          <div className="metric-detail">Due today or overdue</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon blue">♙</div>
          <div className="metric-label">Branch Students</div>
          <div className="metric-value">{data.branch_students_count}</div>
          <div className="metric-detail">Potential outreach</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon green">↗</div>
          <div className="metric-label">Admissions This Month</div>
          <div className="metric-value">{data.admissions_this_month}</div>
          <div className="metric-detail">Enrolled students</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon green">✓</div>
          <div className="metric-label">Conversions This Month</div>
          <div className="metric-value">{data.conversions_this_month}</div>
          <div className="metric-detail">Enquiries converted</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon violet">☎</div>
          <div className="metric-label">Follow-ups Pending</div>
          <div className="metric-value">{data.pending_followups_count}</div>
          <div className="metric-detail">Counselling tasks</div>
        </article>

        <article className="metric-card">
          <div className="metric-icon orange">⚠</div>
          <div className="metric-label">Low Attendance Alerts</div>
          <div className="metric-value">{data.low_attendance_students_count}</div>
          <div className="metric-detail">Attendance &lt; 75%</div>
        </article>
      </section>

      <ChartGrid
        data={data.charts}
        titles={{
          enquiry_funnel: 'Enquiry Pipeline',
          enquiry_sources: 'Lead Sources',
          admissions_trend: 'Admissions Trend',
        }}
      />

      <section className="data-panel counsellor-watchlist-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">ACADEMIC INTERVENTION &amp; RETENTION</span>
            <h2>Student Attendance Watchlist (&lt; 75%)</h2>
          </div>
          <span className="result-count">{data.academic_watchlist.length} students need support</span>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Batch</th>
                <th>Student Phone</th>
                <th>Parent Contact</th>
                <th>Attendance</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data.academic_watchlist.length === 0 ? (
                <tr>
                  <td colSpan={6} className="table-state">
                    All students are attending regularly! No attendance alerts. ✨
                  </td>
                </tr>
              ) : (
                data.academic_watchlist.map((stu) => (
                  <tr key={stu.student_id}>
                    <td>
                      <strong>{stu.student_name}</strong>
                      <small className="muted-block">{stu.student_code}</small>
                    </td>
                    <td>{stu.batch_name}</td>
                    <td>
                      <a href={`tel:${stu.phone}`} className="phone-link">
                        📞 {stu.phone}
                      </a>
                    </td>
                    <td>
                      <a href={`tel:${stu.parent_phone}`} className="phone-link">
                        📞 {stu.parent_name} ({stu.parent_phone})
                      </a>
                    </td>
                    <td>
                      <span className="danger-amount">{stu.attendance_rate}%</span>
                      <small className="muted-block">
                        {stu.attended_classes} / {stu.total_classes} classes
                      </small>
                    </td>
                    <td>
                      <button
                        className="secondary-button btn-sm"
                        onClick={() => setFollowUpMessage(`Follow-up logged for ${stu.student_name}.`)}
                        type="button"
                      >
                        Log Call
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">COUNSELLOR ACTION QUEUE</span>
            <h2>My Assigned Responsibilities</h2>
          </div>
          <button className="primary-button btn-sm" onClick={() => navigate('/enquiries')} type="button">
            + New Student Inquiry
          </button>
        </div>

        <div className="task-list">
          {data.my_responsibilities.length === 0 ? (
            <div className="table-state">No counselling follow-ups pending today.</div>
          ) : (
            data.my_responsibilities.map((r) => (
              <div key={r.id} className="task-item">
                <div>
                  <strong>{r.title}</strong>
                  <div className="task-sub">
                    Dept: {r.department} · Due: {r.due_date || 'No deadline'}
                  </div>
                </div>
                <span className={`status-pill ${r.status === 'completed' ? 'active-status' : 'pending-status'}`}>
                  <i />
                  {r.status.replace('_', ' ')}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </>
  )
}

// -------------------------------------------------------------
// 6. DEFAULT FALLBACK VIEW
// -------------------------------------------------------------
function DefaultFallbackView({
  summary,
  navigate,
}: {
  summary: DashboardSummary | null
  navigate: (path: string) => void
}) {
  const cards = [
    {
      label: 'Total students',
      value: summary ? String(summary.total_students) : '—',
      detail: 'Active student profiles',
      icon: '♙',
      tone: 'blue',
    },
    {
      label: 'Active courses',
      value: summary ? String(summary.active_courses) : '—',
      detail: `${summary?.active_batches ?? '—'} active batches`,
      icon: '▦',
      tone: 'violet',
    },
    {
      label: 'Fee collection',
      value: summary ? `₹${summary.fee_collection.toLocaleString('en-IN')}` : '—',
      detail: 'This month',
      icon: '₹',
      tone: 'green',
    },
    {
      label: 'Attendance rate',
      value: summary ? `${summary.attendance_rate}%` : '—',
      detail: 'Present or late records',
      icon: '✓',
      tone: 'orange',
    },
  ]

  return (
    <>
      <section className="metric-grid">
        {cards.map((card) => (
          <article className="metric-card" key={card.label}>
            <div className={`metric-icon ${card.tone}`}>{card.icon}</div>
            <div className="metric-label">{card.label}</div>
            <div className="metric-value">{card.value}</div>
            <div className="metric-detail">{card.detail}</div>
          </article>
        ))}
      </section>
      <section className="dashboard-grid">
        <article className="data-panel">
          <div className="section-title">
            <h2>Getting Started</h2>
          </div>
          <p>Welcome to your workspace. Use the sidebar to navigate to your assigned modules.</p>
          <button className="primary-button btn-sm" onClick={() => navigate('/students')} type="button">
            Go to Students
          </button>
        </article>
      </section>
    </>
  )
}

export default DashboardPage
