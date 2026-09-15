import { useState, type ReactNode } from 'react'

export type SeriesPoint = { time: string; value: number }
export type ChartSeries = { name: string; points: SeriesPoint[]; color: string; dashed?: boolean }
export type ChartMarker = { id: number | string; time: string; label: string; color: string; kind: string }

function formatTime(value: number) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function TimeSeriesChart({
  title,
  series,
  unit = '%',
  height = 220,
  empty = 'The chart will populate as simulation history is sampled.',
  markers = [],
}: {
  title: string
  series: ChartSeries[]
  unit?: string
  height?: number
  empty?: string
  markers?: ChartMarker[]
}) {
  const [selectedMarker, setSelectedMarker] = useState<ChartMarker | null>(null)
  const visible = series.filter((item) => item.points.length)
  const all = visible.flatMap((item) => item.points.map((point) => ({ ...point, timestamp: new Date(point.time).getTime() })))
  if (all.length < 2) return <div className="chart-empty"><strong>{title}</strong><span>{empty}</span></div>
  const width = 640
  const margin = { left: 48, right: 16, top: 18, bottom: 34 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const minTime = Math.min(...all.map((point) => point.timestamp))
  const maxTime = Math.max(...all.map((point) => point.timestamp))
  const values = all.map((point) => point.value)
  const rawMax = Math.max(...values, unit === '%' ? 100 : 1)
  const rawMin = Math.min(...values, 0)
  const padding = Math.max((rawMax - rawMin) * 0.1, 1)
  const minValue = unit === '%' ? 0 : Math.max(0, rawMin - padding)
  const maxValue = unit === '%' ? Math.max(100, rawMax + padding) : rawMax + padding
  const x = (time: string) => margin.left + ((new Date(time).getTime() - minTime) / Math.max(maxTime - minTime, 1)) * plotWidth
  const y = (value: number) => margin.top + (1 - (value - minValue) / Math.max(maxValue - minValue, 1)) * plotHeight
  const yTicks = [0, .25, .5, .75, 1].map((ratio) => minValue + (maxValue - minValue) * ratio)
  const xTicks = [minTime, minTime + (maxTime - minTime) / 2, maxTime]
  const visibleMarkers = markers.filter((marker) => { const time = new Date(marker.time).getTime(); return time >= minTime && time <= maxTime })
  return (
    <div className="chart-wrap">
      <div className="chart-title-row"><h3>{title}</h3><div className="chart-legend">{visible.map((item) => <span key={item.name}><i style={{ background: item.color }} />{item.name}</span>)}</div></div>
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}, ${visible.map((item) => item.name).join(' versus ')}`}>
        <title>{title}</title>
        {yTicks.map((tick) => <g key={tick}><line x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} className="chart-grid" /><text x={margin.left - 8} y={y(tick) + 4} textAnchor="end">{tick.toFixed(unit === '%' ? 0 : 1)}{unit}</text></g>)}
        {xTicks.map((tick, index) => <text key={`${tick}-${index}`} x={margin.left + ((tick - minTime) / Math.max(maxTime - minTime, 1)) * plotWidth} y={height - 8} textAnchor={index === 0 ? 'start' : index === xTicks.length - 1 ? 'end' : 'middle'}>{formatTime(tick)}</text>)}
        {visible.map((item) => {
          const points = item.points.map((point) => `${x(point.time)},${y(point.value)}`).join(' ')
          const last = item.points[item.points.length - 1]
          return <g key={item.name}>
            <polyline points={points} fill="none" stroke={item.color} strokeWidth="2.2" strokeDasharray={item.dashed ? '6 5' : undefined} vectorEffect="non-scaling-stroke" />
            <circle cx={x(last.time)} cy={y(last.value)} r="3.5" fill={item.color}><title>{item.name}: {last.value.toFixed(1)}{unit}</title></circle>
          </g>
        })}
        {visibleMarkers.map((marker, index) => <g className="chart-event-marker" key={marker.id}>
          <line x1={x(marker.time)} x2={x(marker.time)} y1={margin.top} y2={margin.top + plotHeight} stroke={marker.color} strokeDasharray="3 4" opacity=".42" />
          <circle cx={x(marker.time)} cy={margin.top + 8 + index % 3 * 10} r="5" fill={marker.color} role="button" tabIndex={0} aria-label={marker.label} onClick={() => setSelectedMarker(marker)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedMarker(marker) }}><title>{marker.label}</title></circle>
        </g>)}
        <text className="axis-title" x="12" y={margin.top + plotHeight / 2} transform={`rotate(-90 12 ${margin.top + plotHeight / 2})`} textAnchor="middle">Value ({unit || 'units'})</text>
        <text className="axis-title" x={margin.left + plotWidth / 2} y={height - 1} textAnchor="middle">Simulation time</text>
      </svg>
      {selectedMarker && <button className="chart-marker-detail" onClick={() => setSelectedMarker(null)}><strong>{formatTime(new Date(selectedMarker.time).getTime())} · {selectedMarker.kind}</strong><span>{selectedMarker.label}</span></button>}
    </div>
  )
}

export function DivergingBars({ title, values, unit = ' CPU' }: { title: string; values: Array<{ name: string; value: number }>; unit?: string }) {
  const maximum = Math.max(1, ...values.map((item) => Math.abs(item.value)))
  return <div className="bar-chart" role="img" aria-label={title}>
    <div className="chart-title-row"><h3>{title}</h3><div className="diverging-legend"><span>Deficit</span><span>Surplus</span></div></div>
    {values.map((item) => <div className="diverging-row" key={item.name}>
      <strong>{item.name}</strong>
      <div className="diverging-track"><i className="zero-line" /><span className={item.value >= 0 ? 'positive-bar' : 'negative-bar'} style={{ width: `${Math.abs(item.value) / maximum * 48}%` }} /></div>
      <em className={item.value >= 0 ? 'positive' : 'negative'}>{item.value > 0 ? '+' : ''}{item.value.toFixed(1)}{unit}</em>
    </div>)}
  </div>
}

export function ComparisonBars({ title, rows, value }: { title: string; rows: Array<{ name: string }>; value: (row: { name: string }) => number }) {
  return <div className="comparison-chart" role="img" aria-label={title}>
    <div className="chart-title-row"><h3>{title}</h3><span>0–100%</span></div>
    {rows.map((row) => { const amount = value(row); return <div className="comparison-row" key={row.name}><strong>{row.name}</strong><div><span style={{ width: `${Math.min(100, amount)}%` }} /></div><em>{amount.toFixed(1)}%</em></div> })}
  </div>
}

export function ChartPanel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel chart-panel ${className}`}>{children}</section>
}
