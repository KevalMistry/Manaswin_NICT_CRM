import { useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import type { ReportCatalogEntry, ReportResult } from '../types'

type BranchOption = { id: number; name: string; code: string }
type CourseOption = { id: number; name: string }
type BatchOption = { id: number; name: string; course_id: number; branch_id: number }

function escapeCsv(value: string | number): string {
  const text = String(value ?? '')
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function ReportsPage() {
  const currentUser = useMemo(
    () =>
      JSON.parse(localStorage.getItem('current_user') ?? '{}') as {
        role_name?: string
      },
    [],
  )
  const isSuperAdmin = currentUser.role_name === 'Super Admin'

  const [catalog, setCatalog] = useState<ReportCatalogEntry[]>([])
  const [activeKey, setActiveKey] = useState('')
  const [report, setReport] = useState<ReportResult | null>(null)
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [branchId, setBranchId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [courses, setCourses] = useState<CourseOption[]>([])
  const [batches, setBatches] = useState<BatchOption[]>([])
  const [courseName, setCourseName] = useState('')
  const [batchName, setBatchName] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadedKey, setLoadedKey] = useState('')
  const [error, setError] = useState('')
  const requestKey = activeKey ? `${activeKey}|${branchId}|${courseName}|${batchName}|${dateFrom}|${dateTo}` : ''
  const running = Boolean(requestKey) && loadedKey !== requestKey

  useEffect(() => {
    api
      .get<{ reports: ReportCatalogEntry[] }>('/api/reports/catalog')
      .then(({ data }) => {
        setCatalog(data.reports)
        if (data.reports.length > 0) setActiveKey(data.reports[0].key)
      })
      .catch(() => setError('Unable to load the report catalogue.'))
      .finally(() => setLoading(false))

    if (isSuperAdmin) {
      api
        .get<BranchOption[]>('/api/branches')
        .then(({ data }) => setBranches(data))
        .catch(() => setBranches([]))
    }
    Promise.all([
      api.get<CourseOption[]>('/api/courses'),
      api.get<BatchOption[]>('/api/batches'),
    ]).then(([courseResponse, batchResponse]) => {
      setCourses(courseResponse.data)
      setBatches(batchResponse.data)
    }).catch(() => {
      setCourses([])
      setBatches([])
    })
  }, [isSuperAdmin])

  useEffect(() => {
    if (!activeKey) return
    const key = requestKey
    const params: Record<string, string | number> = {}
    if (branchId) params.branch_id = Number(branchId)
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    if (courseName) params.course_name = courseName
    if (batchName) params.batch_name = batchName
    api
      .get<ReportResult>(`/api/reports/${activeKey}`, { params })
      .then(({ data }) => {
        setReport(data)
        setError('')
      })
      .catch(() => {
        setReport(null)
        setError('Unable to run this report with the selected scope.')
      })
      .finally(() => setLoadedKey(key))
  }, [activeKey, branchId, courseName, batchName, dateFrom, dateTo, requestKey])

  function exportCsv() {
    if (!report) return
    const header = report.columns.map((column) => escapeCsv(column.label)).join(',')
    const lines = report.rows.map((row) =>
      report.columns.map((column) => escapeCsv(row[column.key])).join(','),
    )
    const csv = [header, ...lines].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.key}-${report.generated_at}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  return (
    <section className="module-page reports-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ANALYTICS &amp; EXPORTS</span>
          <h1>Reports Centre</h1>
          <p>Run operational reports, review the totals and export a CSV or print a copy.</p>
        </div>
        <div className="field reports-scope">
          <label htmlFor="report-course">Course</label>
          <select id="report-course" value={courseName} onChange={(event) => setCourseName(event.target.value)}>
            <option value="">All courses</option>
            {courses.map((course) => <option key={course.id} value={course.name}>{course.name}</option>)}
          </select>
        </div>
        <div className="field reports-scope">
          <label htmlFor="report-batch">Batch</label>
          <select id="report-batch" value={batchName} onChange={(event) => setBatchName(event.target.value)}>
            <option value="">All batches</option>
            {batches.filter((batch) => !courseName || courses.find((course) => course.name === courseName)?.id === batch.course_id).map((batch) => <option key={batch.id} value={batch.name}>{batch.name}</option>)}
          </select>
        </div>
        {isSuperAdmin && (
          <div className="field reports-scope">
            <label htmlFor="report-branch">Branch scope</label>
            <select
              id="report-branch"
              value={branchId}
              onChange={(event) => setBranchId(event.target.value)}
            >
              <option value="">All branches</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name} — {branch.code}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field reports-scope">
          <label htmlFor="report-date-from">From date</label>
          <input id="report-date-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </div>
        <div className="field reports-scope">
          <label htmlFor="report-date-to">To date</label>
          <input id="report-date-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}

      {loading ? (
        <div className="table-state">Loading reports…</div>
      ) : catalog.length === 0 ? (
        <div className="table-state">No reports are available for your role.</div>
      ) : (
        <>
          <nav className="report-tabs" aria-label="Report catalogue">
            {catalog.map((item) => (
              <button
                key={item.key}
                type="button"
                className={item.key === activeKey ? 'report-tab active' : 'report-tab'}
                onClick={() => setActiveKey(item.key)}
              >
                {item.title}
              </button>
            ))}
          </nav>

          {running ? (
            <div className="table-state">Running report…</div>
          ) : report ? (
            <>
              <div className="report-header">
                <div>
                  <h2>{report.title}</h2>
                  <p>{report.description}</p>
                  <span className="result-count">
                    Scope: {report.scope} · Generated {report.generated_at}
                  </span>
                </div>
                <div className="report-actions">
                  <button className="secondary-button btn-sm" onClick={exportCsv} type="button">
                    ↓ Export CSV
                  </button>
                  <button
                    className="primary-button btn-sm"
                    onClick={() => window.print()}
                    type="button"
                  >
                    🖨 Print
                  </button>
                </div>
              </div>

              <section className="report-summary">
                {report.summary.map((item) => (
                  <article key={item.label} className="report-summary-card">
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </section>

              <div className="data-panel report-table-panel">
                {report.rows.length === 0 ? (
                  <div className="table-state">No records match this report scope.</div>
                ) : (
                  <div className="table-scroll">
                    <table className="data-table report-table">
                      <thead>
                        <tr>
                          {report.columns.map((column) => (
                            <th key={column.key}>{column.label}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {report.rows.map((row, index) => (
                          <tr key={index}>
                            {report.columns.map((column) => (
                              <td key={column.key}>{row[column.key]}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="table-state">Select a report to view its data.</div>
          )}
        </>
      )}
    </section>
  )
}

export default ReportsPage
