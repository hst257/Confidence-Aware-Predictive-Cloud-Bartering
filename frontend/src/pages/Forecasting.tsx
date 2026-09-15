import { useMemo, useState } from 'react'
import { BrainCircuit, Gauge, History } from 'lucide-react'
import { ChartPanel, TimeSeriesChart } from '../components/Charts'
import type { Snapshot } from '../types'

const palette = ['var(--cyan)', 'var(--violet)', 'var(--amber)', 'var(--green)']

export function Forecasting({ data, providerId, onProviderChange, rangeMinutes, onRangeChange }: { data: Snapshot; providerId: number; onProviderChange: (id: number) => void; rangeMinutes: number; onRangeChange: (minutes: number) => void }) {
  const [resource, setResource] = useState<'CPU' | 'RAM'>('CPU')
  const [model, setModel] = useState(data.simulation.forecast_model === 'Auto' ? (data.simulation.model_assignments[data.selected_provider?.provider.name ?? ''] ?? 'Naive') : data.simulation.forecast_model)
  const [horizon, setHorizon] = useState(60)
  const detail = data.selected_provider
  const forecastSeries = useMemo(() => {
    if (!detail) return []
    const actual = detail.resource_history.map((item) => ({ time: item.simulation_time ?? item.observed_at, value: resource === 'CPU' ? item.cpu_usage : item.ram_usage }))
    const forecasts = detail.predictions.filter((item) => item.model_name === model && item.horizon_minutes === horizon).map((item) => ({ time: item.window_start, value: resource === 'CPU' ? item.predicted_cpu_usage : item.predicted_ram_usage }))
    return [{ name: `Actual ${resource}`, color: palette[0], points: actual }, { name: `${model} +${horizon}m`, color: palette[1], dashed: true, points: forecasts }]
  }, [detail, resource, model, horizon])
  const errorPoints = data.forecasting.error_timeline.filter((item) => item.provider_id === providerId && item.model_name === model && item.horizon_minutes === horizon).map((item) => ({ time: item.time, value: resource === 'CPU' ? item.cpu_error : item.ram_error }))
  const horizonRows = data.forecasting.horizon_metrics.filter((item) => item.model_name === model)
  return <div className="page-stack">
    <section className="panel forecasting-toolbar">
      <div><span className="eyebrow">Strict historical boundary</span><h2>Forecast workbench</h2><p>Every prediction is trained only on samples available at its generation time.</p></div>
      <label>Provider<select value={providerId} onChange={(event) => onProviderChange(Number(event.target.value))}>{data.providers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>Resource<select value={resource} onChange={(event) => setResource(event.target.value as typeof resource)}><option>CPU</option><option>RAM</option></select></label>
      <label>Model<select value={model} onChange={(event) => setModel(event.target.value)}>{data.forecasting.models.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>Horizon<select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>{data.forecasting.horizons.map((item) => <option value={item} key={item}>+{item} min</option>)}</select></label>
      <label>Time range<select value={rangeMinutes} onChange={(event) => onRangeChange(Number(event.target.value))}><option value={120}>2 hours</option><option value={360}>6 hours</option><option value={720}>12 hours</option><option value={1440}>24 hours</option></select></label>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><TimeSeriesChart title={`Actual vs forecast · ${resource}`} unit={resource === 'CPU' ? ' CPU' : ' GB'} series={forecastSeries} /></ChartPanel>
      <ChartPanel><TimeSeriesChart title={`${resource} absolute error over time`} unit={resource === 'CPU' ? ' CPU' : ' GB'} series={[{ name: `${model} error`, color: palette[2], points: errorPoints }]} /></ChartPanel>
    </section>
    <section className="panel table-panel">
      <div className="panel-title-row"><div><span className="eyebrow">Model evaluation</span><h2>Accuracy by model</h2></div><BrainCircuit /></div>
      <div className="responsive-table"><table><thead><tr><th>Model</th><th>Role</th><th>CPU MAE</th><th>RAM MAE</th><th>RMSE</th><th>MAPE</th><th>Bias</th><th>Forecast success</th><th>Fallbacks</th><th>Contracts / SLA failures</th><th>Contract success</th></tr></thead><tbody>{data.forecasting.model_metrics.map((item) => <tr key={item.model_name}><td><strong>{item.model_name}</strong></td><td>{item.decision_forecasts ? 'Decision + shadow' : 'Shadow'}</td><td>{item.cpu_mae.toFixed(2)}</td><td>{item.ram_mae.toFixed(2)}</td><td>{item.rmse.toFixed(2)}</td><td>{item.mape.toFixed(1)}%</td><td>{item.bias.toFixed(2)}</td><td>{item.success_rate.toFixed(1)}%</td><td>{item.fallbacks}</td><td>{item.contracts} / {item.sla_failures}</td><td>{item.model_contract_success_rate.toFixed(1)}%</td></tr>)}</tbody></table></div>
    </section>
    <section className="chart-grid-two">
      <section className="panel table-panel"><div className="panel-title-row"><div><span className="eyebrow">Lead-time sensitivity</span><h2>{model} error by horizon</h2></div><Gauge /></div><div className="horizon-bars" role="img" aria-label={`${model} mean percentage error by forecast horizon`}>{horizonRows.map((item) => <div key={item.horizon_minutes}><strong>+{item.horizon_minutes}m</strong><span><i style={{ width: `${Math.min(100, item.mape)}%` }} /></span><em>{item.mape.toFixed(1)}%</em></div>)}</div><div className="responsive-table"><table><thead><tr><th>Horizon</th><th>Evaluations</th><th>MAE CPU</th><th>MAE RAM</th><th>Success</th></tr></thead><tbody>{horizonRows.map((item) => <tr key={item.horizon_minutes}><td><strong>+{item.horizon_minutes} min</strong></td><td>{item.evaluations}</td><td>{item.cpu_mae.toFixed(2)}</td><td>{item.ram_mae.toFixed(2)}</td><td>{item.success_rate.toFixed(1)}%</td></tr>)}</tbody></table></div></section>
      <section className="panel table-panel"><div className="panel-title-row"><div><span className="eyebrow">Forecast revision tracking</span><h2>Recent revisions</h2></div><History /></div><div className="responsive-table"><table><thead><tr><th>Target</th><th>Model</th><th>Revision</th><th>Prediction</th><th>Uncertainty</th><th>Confidence</th><th>Role</th></tr></thead><tbody>{data.forecasting.revision_tracks.filter((item) => item.provider_id === providerId && item.model_name === model).slice(-12).reverse().map((item) => <tr key={item.prediction_id}><td>{new Date(item.target_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td><td><strong>{item.model_name}</strong>{item.fallback_model && <small>via {item.fallback_model}</small>}</td><td>r{item.revision_number}</td><td>{item.predicted_cpu.toFixed(1)} CPU<small>{item.predicted_ram.toFixed(1)} GB</small></td><td>±{item.uncertainty_cpu.toFixed(1)}<small>±{item.uncertainty_ram.toFixed(1)} GB</small></td><td>{item.confidence.toFixed(1)}%</td><td>{item.decision_forecast ? 'Decision' : 'Shadow'}</td></tr>)}</tbody></table></div></section>
    </section>
    <p className="formula-note"><Gauge size={13} /> Confidence: {data.forecasting.confidence_formula}</p>
  </div>
}
