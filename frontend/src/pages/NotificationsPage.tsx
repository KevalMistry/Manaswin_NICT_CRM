import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'

type NotificationSettings = {
  email_configured: boolean
  whatsapp_configured: boolean
  automation_enabled: boolean
  automation_dry_run: boolean
  automation_channels: string[]
  automation_interval_hours: number
  automation_auto_certificates: boolean
  live_sends_require_confirmation: boolean
}

type PreviewItem = {
  category: string
  channel: string
  recipient: string | null
  student_id: number
  student_name: string
  enrollment_id: number | null
  branch_id: number | null
  subject: string | null
  status: string
  detail: string | null
}

type PreviewResponse = {
  categories: string[]
  channels: string[]
  items: PreviewItem[]
  total: number
  ready: number
  skipped: number
}

type RunResponse = PreviewResponse & {
  dry_run: boolean
  sent: number
  skipped: number
  failed: number
  dry_run_count: number
}

type LogRow = {
  id: number
  category: string
  channel: string
  status: string
  recipient: string | null
  subject: string | null
  error: string | null
  student_name: string | null
  enrollment_id: number | null
  created_at: string
}

const CATEGORIES = [
  { value: 'fee_reminder', label: 'Fee reminders' },
  { value: 'course_completion', label: 'Course completion notices' },
]

const CHANNELS = [
  { value: 'email', label: 'Email' },
  { value: 'whatsapp', label: 'WhatsApp' },
]

function formatDateTime(value: string): string {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function statusClass(status: string): string {
  if (status === 'sent') return 'exam-chip notification-status-ok'
  if (status === 'failed') return 'exam-chip notification-status-fail'
  if (status === 'dry_run' || status === 'ready') return 'exam-chip notification-status-preview'
  return 'exam-chip'
}

function NotificationsPage() {
  const [settings, setSettings] = useState<NotificationSettings | null>(null)
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    CATEGORIES.map((category) => category.value),
  )
  const [selectedChannels, setSelectedChannels] = useState<string[]>(['email'])
  const [daysAhead, setDaysAhead] = useState('7')
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [lastRun, setLastRun] = useState<RunResponse | null>(null)
  const [logs, setLogs] = useState<LogRow[]>([])
  const [logsLoading, setLogsLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadSettings = useCallback(async () => {
    try {
      const { data } = await api.get<NotificationSettings>('/api/notifications/settings')
      setSettings(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load notification settings.'))
    }
  }, [])

  const loadLogs = useCallback(async () => {
    setLogsLoading(true)
    try {
      const { data } = await api.get<LogRow[]>('/api/notifications/logs', {
        params: { limit: 100 },
      })
      setLogs(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the notification log.'))
    } finally {
      setLogsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSettings()
      void loadLogs()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadSettings, loadLogs])

  const queryItems = useMemo(() => {
    const items: [string, string][] = []
    selectedCategories.forEach((category) => items.push(['categories', category]))
    selectedChannels.forEach((channel) => items.push(['channels', channel]))
    items.push(['days_ahead', daysAhead || '0'])
    return items
  }, [selectedCategories, selectedChannels, daysAhead])

  function toggleCategory(value: string) {
    setSelectedCategories((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    )
  }

  function toggleChannel(value: string) {
    setSelectedChannels((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    )
  }

  async function runPreview() {
    if (!selectedCategories.length || !selectedChannels.length) {
      setError('Choose at least one category and one delivery channel.')
      return
    }
    setBusy('preview')
    setError('')
    setMessage('')
    try {
      const { data } = await api.get<PreviewResponse>('/api/notifications/preview', {
        params: new URLSearchParams(queryItems),
      })
      setPreview(data)
      setLastRun(null)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to build the notification preview.'))
    } finally {
      setBusy('')
    }
  }

  async function runJob(dryRun: boolean) {
    if (!selectedCategories.length || !selectedChannels.length) {
      setError('Choose at least one category and one delivery channel.')
      return
    }
    if (!dryRun) {
      const typed = window.prompt(
        `This sends real messages through: ${selectedChannels.join(', ')}. Type SEND to continue.`,
      )
      if (typed !== 'SEND') {
        setMessage('Live delivery cancelled.')
        return
      }
    }
    setBusy(dryRun ? 'dry' : 'live')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<RunResponse>('/api/notifications/run', {
        categories: selectedCategories,
        channels: selectedChannels,
        days_ahead: Number(daysAhead || 0),
        dry_run: dryRun,
        confirm_live: !dryRun,
      })
      setLastRun(data)
      setPreview({
        categories: data.categories,
        channels: data.channels,
        items: data.items,
        total: data.items.length,
        ready: data.dry_run_count,
        skipped: data.skipped,
      })
      setMessage(
        dryRun
          ? `Dry run complete: ${data.dry_run_count} message(s) would be sent, ${data.skipped} skipped.`
          : `Delivery finished: ${data.sent} sent, ${data.skipped} skipped, ${data.failed} failed.`,
      )
      if (!dryRun) await loadLogs()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to run the notification job.'))
    } finally {
      setBusy('')
    }
  }

  const displayItems = preview?.items ?? []
  const readyCount = displayItems.filter((item) => item.status === 'ready').length

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">NOTIFICATIONS</span>
          <h1>Automation & delivery</h1>
          <p>
            Preview and send fee reminders and course-completion notices over
            email or WhatsApp. Live delivery always requires explicit
            confirmation.
          </p>
        </div>
        <span className="result-count">{logs.length} logged attempts</span>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="data-panel notification-settings">
        <div className="section-title">
          <div>
            <span className="eyebrow">DELIVERY HEALTH</span>
            <h2>Channel and scheduler status</h2>
          </div>
        </div>
        <div className="notification-status-grid">
          <div>
            <span>Email</span>
            <strong>{settings?.email_configured ? 'Configured' : 'Not configured'}</strong>
            <small>{settings?.email_configured ? 'SMTP is ready for delivery.' : 'Set SMTP_HOST and SMTP_FROM.'}</small>
          </div>
          <div>
            <span>WhatsApp</span>
            <strong>{settings?.whatsapp_configured ? 'Configured' : 'Not configured'}</strong>
            <small>
              {settings?.whatsapp_configured
                ? 'Meta Cloud API is ready for delivery.'
                : 'Set WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID.'}
            </small>
          </div>
          <div>
            <span>Daily scheduler</span>
            <strong>{settings?.automation_enabled ? 'Enabled' : 'Disabled'}</strong>
            <small>
              {settings?.automation_enabled
                ? `${settings.automation_dry_run ? 'Dry run' : 'Live'} every ${settings.automation_interval_hours}h via ${settings.automation_channels.join(', ')}.`
                : 'Set AUTOMATION_ENABLED=true to start the daily sweep.'}
            </small>
          </div>
          <div>
            <span>Certificate sweep</span>
            <strong>
              {settings?.automation_auto_certificates
                ? settings?.automation_enabled
                  ? settings.automation_dry_run
                    ? 'Dry run'
                    : 'Enabled'
                  : 'On scheduler start'
                : 'Disabled'}
            </strong>
            <small>
              {settings?.automation_auto_certificates
                ? 'Finished courses are checked and eligible certificates issued automatically.'
                : 'Set AUTOMATION_AUTO_CERTIFICATES=true to issue end-of-course certificates.'}
            </small>
          </div>
        </div>
      </section>

      <section className="data-panel notification-runner">
        <div className="section-title">
          <div>
            <span className="eyebrow">JOB BUILDER</span>
            <h2>Choose what to include</h2>
          </div>
        </div>
        <div className="notification-controls">
          <div className="notification-option-group">
            <strong>Categories</strong>
            {CATEGORIES.map((category) => (
              <label key={category.value}>
                <input
                  checked={selectedCategories.includes(category.value)}
                  onChange={() => toggleCategory(category.value)}
                  type="checkbox"
                />
                {category.label}
              </label>
            ))}
          </div>
          <div className="notification-option-group">
            <strong>Channels</strong>
            {CHANNELS.map((channel) => (
              <label key={channel.value}>
                <input
                  checked={selectedChannels.includes(channel.value)}
                  onChange={() => toggleChannel(channel.value)}
                  type="checkbox"
                />
                {channel.label}
              </label>
            ))}
          </div>
          <div className="field notification-days">
            <label htmlFor="notification-days">Fee due window (days)</label>
            <input
              id="notification-days"
              min="0"
              max="90"
              onChange={(event) => setDaysAhead(event.target.value)}
              type="number"
              value={daysAhead}
            />
          </div>
          <div className="notification-run-actions">
            <button
              className="secondary-button"
              disabled={busy === 'preview'}
              onClick={() => void runPreview()}
              type="button"
            >
              {busy === 'preview' ? 'Building…' : 'Preview recipients'}
            </button>
            <button
              className="primary-button"
              disabled={busy !== ''}
              onClick={() => void runJob(true)}
              type="button"
            >
              {busy === 'dry' ? 'Running…' : 'Run dry run'}
            </button>
            <button
              className="danger-button"
              disabled={
                busy !== '' ||
                (!settings?.email_configured && !settings?.whatsapp_configured)
              }
              onClick={() => void runJob(false)}
              type="button"
            >
              {busy === 'live' ? 'Sending…' : 'Send live messages'}
            </button>
          </div>
        </div>
        <p className="notification-hint">
          Fee reminders skip anyone reminded in the last 3 days. Course notices
          are sent once per student and channel. Students without an address or
          phone number, and channels that are not configured, are listed as
          skipped rather than failed.
        </p>
      </section>

      {settings && (settings.email_configured || settings.whatsapp_configured) && selectedChannels.length > 0 && (
        <div className="notification-warning">
          Live delivery is enabled for the selected channel(s). Run a dry run
          first and confirm the recipient list before sending.
        </div>
      )}

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">PREVIEW</span>
            <h2>Planned messages</h2>
          </div>
          <span className="result-count">
            {preview ? `${readyCount} ready · ${preview.skipped} skipped` : 'Not built yet'}
          </span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Category</th>
                <th>Channel</th>
                <th>Recipient</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {displayItems.map((item, index) => (
                <tr key={`${item.student_id}-${item.category}-${item.channel}-${index}`}>
                  <td>
                    <strong>{item.student_name}</strong>
                    <small className="muted-block">enrollment {item.enrollment_id ?? '—'}</small>
                  </td>
                  <td>{item.category === 'fee_reminder' ? 'Fee reminder' : 'Course completion'}</td>
                  <td>{item.channel}</td>
                  <td>{item.recipient ?? '—'}</td>
                  <td>
                    <span className={statusClass(item.status)}>{item.status}</span>
                  </td>
                  <td>{item.detail ?? item.subject ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!displayItems.length && (
            <div className="table-state">
              <strong>Nothing to preview</strong>
              <p>Choose the categories and channels above, then build a preview.</p>
            </div>
          )}
        </div>
      </section>

      {lastRun && (
        <section className="data-panel lms-section-gap">
          <div className="section-title">
            <div>
              <span className="eyebrow">LAST RUN</span>
              <h2>{lastRun.dry_run ? 'Dry run summary' : 'Live delivery summary'}</h2>
            </div>
          </div>
          <div className="notification-metrics">
            <div><strong>{lastRun.sent}</strong><span>Sent</span></div>
            <div><strong>{lastRun.dry_run_count}</strong><span>Would send</span></div>
            <div><strong>{lastRun.skipped}</strong><span>Skipped</span></div>
            <div><strong>{lastRun.failed}</strong><span>Failed</span></div>
          </div>
        </section>
      )}

      <section className="data-panel lms-section-gap">
        <div className="section-title">
          <div>
            <span className="eyebrow">DELIVERY LOG</span>
            <h2>Recent attempts</h2>
          </div>
          <span className="result-count">Latest 100</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Student</th>
                <th>Category</th>
                <th>Channel</th>
                <th>Recipient</th>
                <th>Status</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td>{formatDateTime(log.created_at)}</td>
                  <td>{log.student_name ?? '—'}</td>
                  <td>{log.category === 'fee_reminder' ? 'Fee reminder' : 'Course completion'}</td>
                  <td>{log.channel}</td>
                  <td>{log.recipient ?? '—'}</td>
                  <td>
                    <span className={statusClass(log.status)}>{log.status}</span>
                  </td>
                  <td>{log.error ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!logs.length && !logsLoading && (
            <div className="table-state">
              <strong>No messages logged yet</strong>
              <p>Dry runs are not logged. Live attempts appear here.</p>
            </div>
          )}
          {logsLoading && <div className="table-state">Loading delivery log…</div>}
        </div>
      </section>
    </div>
  )
}

export default NotificationsPage
