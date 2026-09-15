import { Activity, ArrowLeft, ArrowRight, BrainCircuit, CloudOff, Coins, Cpu, Gauge, HardDrive, ShieldCheck, Zap } from 'lucide-react'
import { ChartPanel, TimeSeriesChart, type ChartMarker } from '../components/Charts'
import { StatusBadge } from '../components/StatusBadge'
import type { ProviderAnalytics } from '../types'

export function ProviderDetail({ data, onBack }: { data: ProviderAnalytics | null; onBack: () => void }) {
  if (!data) return <div className="panel empty">Provider analytics are loading…</div>
  const provider = data.provider
  const history = data.resource_history
  const pastPredictions = data.predictions.filter((item) => data.evaluations.some((evaluation) => evaluation.prediction_id === item.id))
  const activePredictions = data.predictions.filter((item) => !item.superseded)
  const markers: ChartMarker[] = data.stochastic_events.map((event) => ({
    id: event.id, time: event.start_time,
    label: `${event.name}: ${event.affected_resource} ${event.event_type === 'workload_drop' ? '−' : '+'}${event.event_type === 'capacity_failure' ? event.capacity_loss_percent : event.magnitude_percent}%`,
    kind: event.event_type.replaceAll('_', ' '),
    color: event.event_type === 'capacity_failure' ? 'var(--red)' : event.event_type === 'workload_drop' ? 'var(--green)' : 'var(--amber)',
  }))
  return <div className="page-stack provider-detail">
    <button className="back-button" onClick={onBack}><ArrowLeft size={15} /> Back to federation</button>
    <section className="provider-detail-hero panel">
      <div><span className="eyebrow">Cloud monitoring detail</span><h2>{provider.name}</h2><p>{provider.personality}. Current stochastic state, forecasts, failures, barter activity, and reputation.</p></div>
      <div className="hero-metrics">
        <div><Cpu /><span>Available CPU</span><strong>{provider.current_state?.cpu_available.toFixed(1)}</strong></div>
        <div><HardDrive /><span>Available RAM</span><strong>{provider.current_state?.ram_available.toFixed(1)} GB</strong></div>
        <div><Activity /><span>Volatility</span><strong>{data.current_volatility.toFixed(2)}</strong></div>
        <div><CloudOff /><span>Capacity lost</span><strong>{provider.capacity_lost_cpu.toFixed(0)} CPU</strong></div>
        <div><Zap /><span>Active event</span><strong>{data.active_stochastic_events[0]?.name ?? 'None'}</strong></div>
        <div><BrainCircuit /><span>Forecast confidence</span><strong>{provider.latest_prediction ? `${provider.latest_prediction.confidence.toFixed(0)}%` : '—'}</strong></div>
        <div><Gauge /><span>Safe CPU commitment</span><strong>{provider.latest_prediction ? `${provider.latest_prediction.safe_cpu_commitment.toFixed(1)} CPU` : '—'}</strong></div>
        <div><Coins /><span>Predictive / emergency</span><strong>{data.predictive_contracts} / {data.emergency_contracts}</strong></div>
        <div><ShieldCheck /><span>SLA / forecast</span><strong>{provider.sla_reputation.toFixed(0)} / {provider.forecast_reliability.toFixed(0)}</strong></div>
      </div>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><TimeSeriesChart title="Workload history" markers={markers} series={[
        { name: 'CPU utilization', color: 'var(--cyan)', points: history.map((item) => ({ time: item.simulation_time!, value: item.cpu_usage / Math.max(item.usable_cpu, 1) * 100 })) },
        { name: 'RAM utilization', color: 'var(--violet)', points: history.map((item) => ({ time: item.simulation_time!, value: item.ram_usage / Math.max(item.usable_ram, 1) * 100 })) },
        { name: 'CPU baseline', color: 'var(--muted)', dashed: true, points: history.map((item) => ({ time: item.simulation_time!, value: item.baseline_cpu / provider.total_cpu * 100 })) },
      ]} /></ChartPanel>
      <ChartPanel><TimeSeriesChart title="Actual vs predicted CPU demand" unit=" CPU" markers={markers} series={[
        { name: 'Actual', color: 'var(--cyan)', points: data.evaluations.map((item) => ({ time: item.simulation_time, value: item.actual_cpu_usage })) },
        { name: 'Predicted', color: 'var(--amber)', dashed: true, points: pastPredictions.map((item) => ({ time: item.window_start, value: item.predicted_cpu_usage })) },
      ]} /></ChartPanel>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><TimeSeriesChart title="Future CPU capacity" unit=" CPU" series={[
        { name: 'Usable', color: 'var(--muted)', dashed: true, points: activePredictions.map((item) => ({ time: item.window_start, value: provider.current_state?.usable_cpu ?? provider.total_cpu })) },
        { name: 'Predicted use', color: 'var(--violet)', points: activePredictions.map((item) => ({ time: item.window_start, value: item.predicted_cpu_usage })) },
        { name: 'Safe barterable', color: 'var(--green)', points: activePredictions.map((item) => ({ time: item.window_start, value: item.safe_cpu_commitment })) },
      ]} /></ChartPanel>
      <section className="panel forecast-score-panel"><span className="eyebrow">Forecast accuracy</span><h3>{data.forecast_metrics.predictions_evaluated} predictions evaluated</h3><div className="forecast-score"><strong>{data.forecast_metrics.success_rate.toFixed(1)}%</strong><span>successful forecasts</span></div><div className="metric-pairs"><div><span>CPU MAE</span><strong>{data.forecast_metrics.cpu_mae.toFixed(2)}</strong></div><div><span>RAM MAE</span><strong>{data.forecast_metrics.ram_mae.toFixed(2)}</strong></div><div><span>Forecast bias</span><strong>{data.forecast_metrics.forecast_bias.toFixed(2)}</strong></div><div><span>Event impacted</span><strong>{data.forecast_metrics.event_impacted_forecasts}</strong></div><div><span>Mean % error</span><strong>{data.forecast_metrics.percentage_error.toFixed(2)}%</strong></div><div><span>Avg confidence</span><strong>{data.forecast_metrics.average_confidence.toFixed(1)}%</strong></div></div></section>
    </section>
    <section className="panel table-panel"><div className="panel-title-row"><div><span className="eyebrow">Incoming & outgoing</span><h2>Contracts</h2></div><span className="count-pill">{data.contracts.length}</span></div><div className="responsive-table"><table><thead><tr><th>Agreement</th><th>Direction</th><th>Resources</th><th>Window</th><th>Status</th></tr></thead><tbody>{data.contracts.map((contract) => <tr key={contract.id}><td><strong>#{contract.id}</strong><small>{contract.barter_type} · {contract.parent_contract_id ? `replacement for #${contract.parent_contract_id}` : 'original'}</small></td><td>{contract.provider_id === provider.id ? <>{provider.name} <ArrowRight className="inline-icon" size={13} /> {contract.consumer_name}</> : <>{contract.provider_name} <ArrowRight className="inline-icon" size={13} /> {provider.name}</>}</td><td>{contract.cpu_amount.toFixed(1)} CPU<small>{contract.ram_amount.toFixed(1)} GB RAM</small></td><td>{new Date(contract.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}<small>to {new Date(contract.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></td><td><StatusBadge status={contract.status} /></td></tr>)}</tbody></table></div></section>
    <section className="detail-columns">
      <div className="panel detail-list"><div className="panel-title-row"><h3><Coins size={16} /> Credit history</h3><span>{data.transactions.length}</span></div>{data.transactions.slice(-12).reverse().map((item) => <div className="history-row" key={item.id}><div><strong>{item.transaction_type}</strong><span>{item.description}</span></div><strong className={item.amount >= 0 ? 'positive' : 'negative'}>{item.amount > 0 ? '+' : ''}{item.amount.toFixed(2)}</strong></div>)}</div>
      <div className="panel detail-list"><div className="panel-title-row"><h3><ShieldCheck size={16} /> Reputation history</h3><span>{data.reputation_history.length}</span></div>{data.reputation_history.slice(-12).reverse().map((item) => <div className="history-row" key={item.id}><div><strong>{item.metric}</strong><span>{item.reason}</span></div><strong>{item.old_value.toFixed(1)} → {item.new_value.toFixed(1)}</strong></div>)}</div>
      <div className="panel detail-list"><div className="panel-title-row"><h3><Cpu size={16} /> Future reservations</h3><span>{data.future_reservations.length}</span></div>{data.future_reservations.length ? data.future_reservations.map((item) => <div className="reservation-row" key={item.id}><span>{item.barter_type} #{item.id} · {new Date(item.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><strong>{item.cpu_amount.toFixed(1)} CPU · {item.ram_amount.toFixed(1)} GB</strong></div>) : <div className="empty compact">No capacity currently reserved.</div>}</div>
    </section>
    <section className="panel table-panel"><div className="panel-title-row"><div><span className="eyebrow">Stochastic history</span><h2>Capacity failures & workload events</h2></div><span className="count-pill">{data.stochastic_events.length}</span></div><div className="responsive-table"><table><thead><tr><th>Event</th><th>Resource</th><th>Magnitude</th><th>Window</th><th>Source</th></tr></thead><tbody>{data.stochastic_events.slice(0, 20).map((event) => <tr key={event.id}><td><strong>{event.name}</strong><small>{event.event_type.replaceAll('_', ' ')}</small></td><td>{event.affected_resource}</td><td>{event.event_type === 'capacity_failure' ? `${event.capacity_loss_percent}% lost` : `${event.event_type === 'workload_drop' ? '−' : '+'}${event.magnitude_percent.toFixed(1)}%`}</td><td>{new Date(event.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}<small>to {new Date(event.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></td><td>{event.source}</td></tr>)}</tbody></table></div></section>
  </div>
}
