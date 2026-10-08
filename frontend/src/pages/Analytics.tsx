import { PulseIcon, BrainIcon, CoinsIcon, GaugeIcon, HandshakeIcon, HeartbeatIcon, ArrowsCounterClockwiseIcon, ShieldCheckIcon, SirenIcon } from '@phosphor-icons/react'
import { ChartPanel, ComparisonBars, TimeSeriesChart } from '../components/Charts'
import type { Snapshot } from '../types'

const palette = ['var(--cyan)', 'var(--violet)', 'var(--amber)', 'var(--green)']

export function Analytics({ data }: { data: Snapshot }) {
  const metrics = data.analytics
  const reputationByProvider = data.providers.map((provider, index) => ({
    name: provider.name, color: palette[index],
    points: data.reputation.filter((item) => item.provider_id === provider.id && item.metric === 'Forecast reliability').map((item) => ({ time: item.simulation_time ?? item.created_at, value: item.new_value })),
  }))
  return <div className="page-stack">
    <section className="run-summary panel">
      <div><span className="eyebrow">Simulation run #{data.simulation.run_id}</span><h2>{data.simulation.scenario} · Seed {data.simulation.seed}</h2><p>{data.simulation.mode} mode · Day {data.simulation.day} {data.simulation.clock}</p></div>
      <div><strong>{metrics.system_resilience_score.toFixed(1)}</strong><span>System resilience</span><small>Project-specific metric</small></div>
      <div><strong>{metrics.average_forecast_accuracy.toFixed(1)}%</strong><span>Forecast accuracy</span><small>{metrics.forecast_metrics.reduce((sum, item) => sum + item.event_impacted_forecasts, 0)} event-impacted forecasts</small></div>
      <div><strong>{metrics.cpu_hours_exchanged.toFixed(1)}</strong><span>CPU-hours exchanged</span><small>{metrics.ram_hours_exchanged.toFixed(1)} RAM-hours</small></div>
    </section>
    <section className="analysis-kpis">
      <div className="analysis-kpi panel"><ShieldCheckIcon /><span>Predictive prevention</span><strong>{metrics.shortages_prevented}</strong><small>{metrics.predictive_contracts} predictive contracts</small></div>
      <div className="analysis-kpi panel"><SirenIcon /><span>Reactive recovery</span><strong>{metrics.emergency_recoveries}</strong><small>{metrics.emergency_contracts} emergency contracts</small></div>
      <div className="analysis-kpi panel"><PulseIcon /><span>Unresolved shortages</span><strong>{metrics.unresolved_shortages}</strong><small>{metrics.average_reaction_time.toFixed(1)} min mean reaction</small></div>
      <div className="analysis-kpi panel"><HandshakeIcon /><span>Idle capacity shared</span><strong>{metrics.idle_capacity_shared.toFixed(1)}</strong><small>{metrics.providers_helped} providers helped</small></div>
      <div className="analysis-kpi panel"><CoinsIcon /><span>Credit circulation</span><strong>{metrics.credit_circulation.toFixed(1)}</strong><small>{metrics.collateral_penalties.toFixed(1)} penalties</small></div>
      <div className="analysis-kpi panel"><ArrowsCounterClockwiseIcon /><span>Failure recovery</span><strong>{metrics.failure_recovery_rate.toFixed(1)}%</strong><small>{metrics.renegotiation_rate.toFixed(1)}% renegotiated</small></div>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><ComparisonBars title="Provider CPU utilization" rows={metrics.providers} value={(row) => metrics.providers.find((item) => item.name === row.name)?.cpu_utilization ?? 0} /></ChartPanel>
      <ChartPanel><ComparisonBars title="Recent workload volatility" rows={metrics.providers} value={(row) => Math.min(100, (metrics.providers.find((item) => item.name === row.name)?.volatility ?? 0) * 12)} /></ChartPanel>
    </section>
    <section className="chart-grid-two">
      <ChartPanel>
        <div className="chart-title-row"><h3>Predictive vs reactive bartering</h3><span>Academic comparison</span></div>
        <div className="comparison-matrix"><div><span>Predictive contracts</span><strong>{metrics.predictive_contracts}</strong></div><div><span>Emergency contracts</span><strong>{metrics.emergency_contracts}</strong></div><div><span>Prevented before occurrence</span><strong>{metrics.shortages_prevented}</strong></div><div><span>Handled reactively</span><strong>{metrics.emergency_recoveries}</strong></div><div><span>Failed shortages</span><strong>{metrics.unresolved_shortages}</strong></div><div><span>Collateral penalties</span><strong>{metrics.collateral_penalties.toFixed(1)}</strong></div></div>
      </ChartPanel>
      <ChartPanel>
        <div className="chart-title-row"><h3>Barter efficiency</h3><span>Resource-time measures</span></div>
        <div className="comparison-matrix"><div><span>Utilization before barter</span><strong>{metrics.utilization_before_barter.toFixed(1)}%</strong></div><div><span>Utilization after barter</span><strong>{metrics.utilization_after_barter.toFixed(1)}%</strong></div><div><span>CPU-hours</span><strong>{metrics.cpu_hours_exchanged.toFixed(1)}</strong></div><div><span>RAM-hours</span><strong>{metrics.ram_hours_exchanged.toFixed(1)}</strong></div><div><span>Contract success</span><strong>{metrics.contract_success_rate.toFixed(1)}%</strong></div><div><span>Credits transferred</span><strong>{metrics.credit_circulation.toFixed(1)}</strong></div></div>
      </ChartPanel>
    </section>
    <section className="panel table-panel calibration-panel"><div className="panel-title-row"><div><span className="eyebrow">Research validation</span><h2>Forecast confidence calibration</h2></div><GaugeIcon /></div><div className="responsive-table"><table><thead><tr><th>Confidence bucket</th><th>Predictions</th><th>Average confidence</th><th>Observed success</th><th>Average error</th><th>Calibration</th></tr></thead><tbody>{metrics.confidence_calibration.map((bucket) => <tr key={bucket.bucket}><td><strong>{bucket.bucket}</strong></td><td>{bucket.prediction_count}</td><td>{bucket.average_confidence.toFixed(1)}%</td><td>{bucket.success_rate.toFixed(1)}%</td><td>{bucket.average_error.toFixed(1)}%</td><td><div className="calibration-track"><i style={{ width: `${bucket.average_confidence}%` }} /><b style={{ width: `${bucket.success_rate}%` }} /></div></td></tr>)}</tbody></table></div></section>
    <section className="chart-grid-two">
      <ChartPanel><TimeSeriesChart title="Barter-credit balances" unit=" cr" series={data.credit_timelines.map((timeline, index) => ({ name: timeline.provider_name, color: palette[index], points: timeline.points.map((point) => ({ time: point.time, value: point.balance })) }))} /></ChartPanel>
      <ChartPanel><TimeSeriesChart title="Forecast reliability over observations" series={reputationByProvider} /></ChartPanel>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><div className="chart-title-row"><h3>Contract outcomes</h3><span>{metrics.barter_transactions} total</span></div><div className="outcome-bars">{['Completed', 'Active', 'Scheduled', 'At Risk', 'Renegotiated', 'Failed'].map((status) => { const count = metrics.contract_counts[status] ?? 0; return <div key={status}><span>{status}</span><div><i className={`outcome-${status.toLowerCase().replace(' ', '-')}`} style={{ width: `${metrics.barter_transactions ? count / metrics.barter_transactions * 100 : 0}%` }} /></div><strong>{count}</strong></div> })}</div></ChartPanel>
      <ChartPanel><div className="chart-title-row"><h3>Forecast error analysis</h3><span>Unexpected events remain hidden</span></div><div className="responsive-table"><table><thead><tr><th>Provider</th><th>CPU MAE</th><th>RAM MAE</th><th>Bias</th><th>Error</th><th>Confidence</th><th>Event impacted</th></tr></thead><tbody>{metrics.forecast_metrics.map((item) => <tr key={item.provider_id}><td><strong>{item.provider_name}</strong></td><td>{item.cpu_mae.toFixed(2)}</td><td>{item.ram_mae.toFixed(2)}</td><td>{item.forecast_bias.toFixed(2)}</td><td>{item.percentage_error.toFixed(1)}%</td><td>{item.average_confidence.toFixed(1)}%</td><td>{item.event_impacted_forecasts}</td></tr>)}</tbody></table></div></ChartPanel>
    </section>
    <section className="panel table-panel"><div className="panel-title-row"><div><span className="eyebrow">Run history</span><h2>Comparable simulation runs</h2></div><BrainIcon /></div><div className="responsive-table"><table><thead><tr><th>Run</th><th>Scenario</th><th>Seed</th><th>Duration</th><th>Status</th></tr></thead><tbody>{metrics.runs.map((run) => <tr key={run.id}><td><strong>#{run.id}</strong></td><td>{run.scenario}</td><td>{run.seed}</td><td>{run.simulation_duration_minutes.toFixed(0)} min</td><td>{run.status}</td></tr>)}</tbody></table></div><p className="formula-note"><HeartbeatIcon size={13} /> {metrics.resilience_formula}</p></section>
  </div>
}
