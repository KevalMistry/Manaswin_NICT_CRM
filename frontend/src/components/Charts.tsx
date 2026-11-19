import type { ReactNode } from 'react'
import type { ChartData } from '../types'

type ChartProps = {
  data: ChartData
  title?: string
  subtitle?: string
  height?: number
}

const PALETTE = [
  '#4f46e5',
  '#0ea5e9',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#14b8a6',
  '#ec4899',
]

function formatChartValue(value: number, valueFormat: ChartData['value_format']): string {
  if (valueFormat === 'currency') {
    return `₹${Math.round(value).toLocaleString('en-IN')}`
  }
  if (valueFormat === 'percent') {
    return `${value.toFixed(1)}%`
  }
  return value.toLocaleString('en-IN')
}

function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return step * magnitude
}

function ChartShell({ title, subtitle, children }: {
  title?: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <article className="chart-card">
      {title && (
        <div className="chart-header">
          <div>
            <h3>{title}</h3>
            {subtitle && <p>{subtitle}</p>}
          </div>
        </div>
      )}
      <div className="chart-body">{children}</div>
    </article>
  )
}

function EmptyChart() {
  return <div className="chart-empty">No data recorded yet.</div>
}

function LineChart({ data, height = 220 }: { data: ChartData; height?: number }) {
  const series = data.series[0]
  if (!series || series.data.length === 0) return <EmptyChart />
  const width = 640
  const padding = { top: 16, right: 18, bottom: 34, left: 54 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const max = niceMax(Math.max(...series.data, 1))
  const stepX = series.data.length > 1 ? innerWidth / (series.data.length - 1) : 0
  const points = series.data.map((value, index) => ({
    x: padding.left + (series.data.length > 1 ? index * stepX : innerWidth / 2),
    y: padding.top + innerHeight - (value / max) * innerHeight,
    value,
  }))
  const baseline = padding.top + innerHeight
  const labelEvery = data.labels.length > 8 ? 2 : 1

  return (
    <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Line chart">
      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
        const y = padding.top + innerHeight * ratio
        return (
          <g key={ratio}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-gridline" />
            <text x={padding.left - 8} y={y + 4} className="chart-axis-label" textAnchor="end">
              {formatChartValue(max * (1 - ratio), data.value_format)}
            </text>
          </g>
        )
      })}
      {data.labels.map((label, index) =>
        index % labelEvery === 0 ? (
          <text
            key={label + index}
            x={points[index].x}
            y={height - 12}
            className="chart-axis-label"
            textAnchor="middle"
          >
            {label}
          </text>
        ) : null,
      )}
      <polyline
        className="chart-line"
        points={points.map((point) => `${point.x},${point.y}`).join(' ')}
        fill="none"
      />
      {points.map((point, index) => (
        <g key={`line-point-${index}`}>
          <circle cx={point.x} cy={point.y} r={4} className="chart-point">
            <title>{`${data.labels[index]}: ${formatChartValue(point.value, data.value_format)}`}</title>
          </circle>
        </g>
      ))}
      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={baseline}
        y2={baseline}
        className="chart-axis"
      />
    </svg>
  )
}

function BarChart({ data, height = 220 }: { data: ChartData; height?: number }) {
  const series = data.series[0]
  if (!series || series.data.length === 0) return <EmptyChart />
  const width = 640
  const padding = { top: 16, right: 18, bottom: 36, left: 54 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const max = niceMax(Math.max(...series.data, 1))
  const slot = innerWidth / series.data.length
  const barWidth = Math.min(44, slot * 0.6)
  const baseline = padding.top + innerHeight
  const labelEvery = data.labels.length > 8 ? 2 : 1

  return (
    <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Bar chart">
      {[0, 0.5, 1].map((ratio) => {
        const y = padding.top + innerHeight * ratio
        return (
          <g key={ratio}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-gridline" />
            <text x={padding.left - 8} y={y + 4} className="chart-axis-label" textAnchor="end">
              {formatChartValue(max * (1 - ratio), data.value_format)}
            </text>
          </g>
        )
      })}
      {series.data.map((value, index) => {
        const barHeight = (value / max) * innerHeight
        const x = padding.left + index * slot + (slot - barWidth) / 2
        return (
          <g key={`bar-${index}`}>
            <rect
              x={x}
              y={baseline - barHeight}
              width={barWidth}
              height={Math.max(barHeight, value > 0 ? 2 : 0)}
              rx={5}
              fill={PALETTE[index % PALETTE.length]}
            >
              <title>{`${data.labels[index]}: ${formatChartValue(value, data.value_format)}`}</title>
            </rect>
            {index % labelEvery === 0 && (
              <text
                x={x + barWidth / 2}
                y={height - 12}
                className="chart-axis-label"
                textAnchor="middle"
              >
                {data.labels[index]}
              </text>
            )}
          </g>
        )
      })}
      <line x1={padding.left} x2={width - padding.right} y1={baseline} y2={baseline} className="chart-axis" />
    </svg>
  )
}

function HBarChart({ data }: { data: ChartData }) {
  const series = data.series[0]
  if (!series || series.data.length === 0) return <EmptyChart />
  const width = 640
  const labelWidth = 168
  const valueWidth = 84
  const rowHeight = 34
  const padding = { top: 10, right: valueWidth, bottom: 10 }
  const height = Math.max(140, data.labels.length * rowHeight + padding.top + padding.bottom)
  const innerWidth = width - labelWidth - valueWidth
  const max = Math.max(...series.data, 1)

  return (
    <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Horizontal bar chart">
      {series.data.map((value, index) => {
        const barWidth = (value / max) * innerWidth
        const y = padding.top + index * rowHeight
        return (
          <g key={`hbar-${index}`}>
            <text x={labelWidth - 10} y={y + 21} className="chart-axis-label" textAnchor="end">
              {data.labels[index].length > 22 ? `${data.labels[index].slice(0, 21)}…` : data.labels[index]}
            </text>
            <rect
              x={labelWidth}
              y={y + 7}
              width={Math.max(barWidth, value > 0 ? 3 : 0)}
              height={rowHeight - 14}
              rx={4}
              fill={PALETTE[index % PALETTE.length]}
            >
              <title>{`${data.labels[index]}: ${formatChartValue(value, data.value_format)}`}</title>
            </rect>
            <text x={labelWidth + barWidth + 8} y={y + 21} className="chart-value-label">
              {formatChartValue(value, data.value_format)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function DonutChart({ data }: { data: ChartData }) {
  const series = data.series[0]
  if (!series || series.data.length === 0) return <EmptyChart />
  const total = series.data.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return <EmptyChart />

  const size = 200
  const radius = 74
  const stroke = 26
  const circumference = 2 * Math.PI * radius
  const segments = series.data.map((value, index) => ({
    dash: (value / total) * circumference,
    offset:
      (series.data.slice(0, index).reduce((sum, item) => sum + item, 0) / total) *
      circumference,
  }))

  return (
    <div className="donut-layout">
      <svg className="chart-donut" viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Donut chart">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#eef1f7" strokeWidth={stroke} />
        {series.data.map((value, index) => (
          <circle
            key={`donut-${index}`}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={PALETTE[index % PALETTE.length]}
            strokeWidth={stroke}
            strokeDasharray={`${segments[index].dash} ${circumference - segments[index].dash}`}
            strokeDashoffset={-segments[index].offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            strokeLinecap="butt"
          >
            <title>{`${data.labels[index]}: ${formatChartValue(value, data.value_format)}`}</title>
          </circle>
        ))}
        <text x={size / 2} y={size / 2 - 2} textAnchor="middle" className="donut-total">
          {formatChartValue(total, data.value_format)}
        </text>
        <text x={size / 2} y={size / 2 + 18} textAnchor="middle" className="donut-caption">
          Total
        </text>
      </svg>
      <ul className="donut-legend">
        {data.labels.map((label, index) => (
          <li key={label + index}>
            <span className="legend-dot" style={{ background: PALETTE[index % PALETTE.length] }} />
            <span className="legend-label">{label}</span>
            <span className="legend-value">{formatChartValue(series.data[index], data.value_format)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ChartCard({ data, title, subtitle }: ChartProps) {
  if (!data) return null
  const body =
    data.type === 'line' ? (
      <LineChart data={data} />
    ) : data.type === 'hbar' ? (
      <HBarChart data={data} />
    ) : data.type === 'donut' ? (
      <DonutChart data={data} />
    ) : (
      <BarChart data={data} />
    )

  return (
    <ChartShell title={title} subtitle={subtitle}>
      {body}
    </ChartShell>
  )
}

export function ChartGrid({ data, titles }: {
  data?: Record<string, ChartData>
  titles: Record<string, string>
}) {
  if (!data) return null
  const entries = Object.entries(titles).filter(([key]) => data[key])
  if (entries.length === 0) return null
  return (
    <section className="chart-grid">
      {entries.map(([key, title]) => (
        <ChartCard key={key} data={data[key]} title={title} />
      ))}
    </section>
  )
}
