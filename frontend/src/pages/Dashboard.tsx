import { useState } from 'react'
import { Activity, AlertTriangle, BrainCircuit, CircleCheck, Coins, Cpu, Gauge, HardDrive, HeartPulse, Server, ShieldCheck, Siren, TrendingDown, TrendingUp, Zap } from 'lucide-react'
import { ChartPanel, DivergingBars, TimeSeriesChart, type ChartMarker } from '../components/Charts'
import { Meter } from '../components/Meter'
import type { Provider, Snapshot } from '../types'

function ProviderCard({ provider, selected, onSelect, onDetails }: { provider: Provider; selected: boolean; onSelect: () => void; onDetails: () => void }) {
  const state = provider.current_state
  const prediction = provider.latest_prediction
  const cpuPercent = state ? state.cpu_usage / Math.max(state.usable_cpu, 1) * 100 : 0
  const ramPercent = state ? state.ram_usage / Math.max(state.usable_ram, 1) * 100 : 0
  const deficit = Boolean(prediction && (prediction.cpu_deficit > 0 || prediction.ram_deficit > 0))
  const impaired = provider.capacity_lost_cpu > 0 || provider.capacity_lost_ram > 0
  return <article className={`provider-live-card panel ${selected ? 'selected' : ''} ${deficit || impaired ? 'at-risk' : ''}`} onClick={onSelect}>
    <div className="provider-head"><div className="provider-icon"><Server size={19} /></div><div><h3>{provider.name}</h3><span>{provider.personality}</span></div><i className={`health-dot ${deficit || impaired ? 'amber' : 'green'}`} /></div>
    {provider.active_event && <div className="active-event-chip"><Zap size={12} /> {provider.active_event}</div>}
    <div className="util-pair">
      <div><span><Cpu size={13} /> CPU</span><strong>{cpuPercent.toFixed(1)}%</strong><Meter value={cpuPercent} total={100} tone={cpuPercent > 90 ? 'amber' : 'cyan'} /><small>{state?.cpu_available.toFixed(1) ?? '—'} available · {state?.usable_cpu.toFixed(0) ?? provider.total_cpu} usable</small></div>
      <div><span><HardDrive size={13} /> RAM</span><strong>{ramPercent.toFixed(1)}%</strong><Meter value={ramPercent} total={100} tone={ramPercent > 90 ? 'amber' : 'violet'} /><small>{state?.ram_available.toFixed(1) ?? '—'} GB available</small></div>
    </div>
    <div className={`forecast-strip ${deficit ? 'deficit' : 'surplus'}`}>
      {deficit ? <TrendingDown size={15} /> : <TrendingUp size={15} />}
      <span>{!prediction ? 'Awaiting first cycle' : deficit ? `${prediction.cpu_deficit.toFixed(1)} CPU deficit` : `${prediction.safe_cpu_commitment.toFixed(1)} safe CPU surplus`}</span>
      <strong>{prediction ? `${prediction.confidence}%` : '—'}</strong>
    </div>
    <div className="provider-metric-grid">
      <div><Activity /><span>Volatility</span><strong>{provider.current_volatility.toFixed(2)}</strong></div>
      <div><AlertTriangle /><span>Capacity lost</span><strong>{provider.capacity_lost_cpu.toFixed(0)} CPU</strong></div>
      <div><Coins /><span>Credits / collateral</span><strong>{provider.credit_balance.toFixed(0)} / {provider.locked_collateral.toFixed(1)}</strong></div>
      <div><Gauge /><span>SLA / forecast</span><strong>{provider.sla_reputation.toFixed(0)} / {provider.forecast_reliability.toFixed(0)}</strong></div>
    </div>
    <button className="card-detail-button" onClick={(event) => { event.stopPropagation(); onDetails() }}>View details</button>
  </article>
}

function markersFor(data: Snapshot, providerId: number): ChartMarker[] {
  const stochastic: ChartMarker[] = data.stochastic_events.filter((event) => event.provider_id === providerId).map((event) => ({
    id: `s-${event.id}`, time: event.start_time,
    label: `${event.provider_name}: ${event.name} · ${event.affected_resource} ${event.event_type === 'workload_drop' ? '−' : '+'}${event.event_type === 'capacity_failure' ? event.capacity_loss_percent : event.magnitude_percent}%`,
    kind: event.event_type.replaceAll('_', ' '),
    color: event.event_type === 'capacity_failure' ? 'var(--red)' : event.event_type === 'workload_drop' ? 'var(--green)' : 'var(--amber)',
  }))
  const responses: ChartMarker[] = data.events.filter((event) => event.provider_id === providerId && /contract\.(created|at_risk|activated|renegotiated)|emergency\./.test(event.event_type)).map((event) => ({
    id: `e-${event.id}`, time: event.simulation_time ?? event.created_at, label: event.message,
    kind: event.event_type.replaceAll('.', ' '), color: event.event_type.includes('at_risk') ? 'var(--red)' : 'var(--cyan)',
  }))
  return [...stochastic, ...responses]
}

export function Dashboard({ data, selectedProviderId, onSelectProvider, onProviderDetails, rangeMinutes, onRangeChange }: {
  data: Snapshot; selectedProviderId: number; onSelectProvider: (id: number) => void; onProviderDetails: (id: number) => void
  rangeMinutes: number; onRangeChange: (minutes: number) => void
}) {
  const [resource, setResource] = useState<'CPU' | 'RAM'>('CPU')
  const selected = data.selected_provider
  const provider = selected?.provider
  const history = selected?.resource_history ?? []
  const future = data.predictions.filter((item) => item.provider_id === selectedProviderId)
  const position = data.providers.map((item) => {
    const prediction = item.latest_prediction
    return { name: item.name, value: prediction ? prediction.cpu_deficit ? -prediction.cpu_deficit : prediction.safe_cpu_commitment : 0 }
  })
  const evaluatedPredictions = selected?.predictions.filter((item) => new Date(item.window_start) <= new Date(data.simulation.current_time)) ?? []
  const markers = markersFor(data, selectedProviderId)
  const currentUsable = resource === 'CPU' ? provider?.current_state?.usable_cpu ?? provider?.total_cpu ?? 0 : provider?.current_state?.usable_ram ?? provider?.total_ram ?? 0
  return <div className="page-stack">
    <section className="phase3-status-grid">
      <div className="kpi"><Zap /><div><span>Active events</span><strong>{data.analytics.active_events}</strong><small>{data.analytics.active_failures} capacity failures</small></div></div>
      <div className="kpi"><ShieldCheck /><div><span>Contract posture</span><strong>{data.analytics.active_contracts} active</strong><small>{data.analytics.at_risk_contracts} at risk · {data.analytics.predictive_contracts} predictive</small></div></div>
      <div className="kpi"><BrainCircuit /><div><span>Forecast demand</span><strong>{data.analytics.predicted_deficits}</strong><small>{data.analytics.current_emergencies} current emergencies</small></div></div>
      <div className="kpi"><CircleCheck /><div><span>Shortages prevented</span><strong>{data.analytics.shortages_prevented}</strong><small>{data.analytics.emergency_recoveries} emergency recoveries</small></div></div>
      <div className="kpi"><Siren /><div><span>Unresolved shortages</span><strong>{data.analytics.unresolved_shortages}</strong><small>{data.analytics.average_reaction_time.toFixed(1)} min average reaction</small></div></div>
      <div className="kpi"><HeartPulse /><div><span>System resilience</span><strong>{data.analytics.system_resilience_score.toFixed(1)}</strong><small>Project-specific simulation score</small></div></div>
      <div className="kpi"><Activity /><div><span>Federation utilization</span><strong>{data.analytics.total_cpu_utilization.toFixed(1)}%</strong><small>{data.analytics.total_ram_utilization.toFixed(1)}% usable RAM</small></div></div>
      <div className="kpi"><BrainCircuit /><div><span>Forecast accuracy</span><strong>{data.analytics.average_forecast_accuracy ? `${data.analytics.average_forecast_accuracy.toFixed(1)}%` : 'Learning'}</strong><small>{data.analytics.forecast_metrics.reduce((sum, item) => sum + item.predictions_evaluated, 0)} evaluated</small></div></div>
    </section>

    <div className="section-heading"><div><span className="eyebrow">Live stochastic federation</span><h2>Provider resources</h2></div><span className="updated">Correlated minute samples · events hidden from forecasts</span></div>
    <section className="provider-live-grid">{data.providers.map((item) => <ProviderCard key={item.id} provider={item} selected={item.id === selectedProviderId} onSelect={() => onSelectProvider(item.id)} onDetails={() => onProviderDetails(item.id)} />)}</section>

    <section className="analytics-toolbar">
      <div><span className="eyebrow">Selected provider</span><h2>{provider?.name ?? 'Provider'} telemetry</h2></div>
      <div className="segmented" aria-label="History period">{[[30, '30m'], [60, '1h'], [360, '6h'], [720, '12h'], [1440, '24h']].map(([value, label]) => <button key={value} className={rangeMinutes === value ? 'active' : ''} onClick={() => onRangeChange(Number(value))}>{label}</button>)}</div>
    </section>
    <section className="chart-grid-two">
      <ChartPanel><TimeSeriesChart title="Live resource utilization" markers={markers} series={[
        { name: 'CPU utilization', color: 'var(--cyan)', points: history.map((item) => ({ time: item.simulation_time!, value: item.cpu_usage / Math.max(item.usable_cpu, 1) * 100 })) },
        { name: 'RAM utilization', color: 'var(--violet)', points: history.map((item) => ({ time: item.simulation_time!, value: item.ram_usage / Math.max(item.usable_ram, 1) * 100 })) },
        { name: 'CPU baseline', color: 'var(--muted)', dashed: true, points: history.map((item) => ({ time: item.simulation_time!, value: item.baseline_cpu / Math.max(provider?.total_cpu ?? 1, 1) * 100 })) },
      ]} /></ChartPanel>
      <ChartPanel><DivergingBars title="Predicted federation position" values={position} /></ChartPanel>
    </section>
    <section className="chart-grid-two">
      <ChartPanel>
        <div className="chart-switch"><span className="eyebrow">Forecast validation</span><div className="segmented"><button className={resource === 'CPU' ? 'active' : ''} onClick={() => setResource('CPU')}>CPU</button><button className={resource === 'RAM' ? 'active' : ''} onClick={() => setResource('RAM')}>RAM</button></div></div>
        <TimeSeriesChart title="Actual vs predicted usage" unit={resource === 'RAM' ? ' GB' : ' CPU'} markers={markers} series={[
          { name: 'Actual usage', color: 'var(--cyan)', points: (selected?.evaluations ?? []).map((item) => ({ time: item.simulation_time, value: resource === 'CPU' ? item.actual_cpu_usage : item.actual_ram_usage })) },
          { name: 'Predicted usage', color: 'var(--amber)', dashed: true, points: evaluatedPredictions.map((item) => ({ time: item.window_start, value: resource === 'CPU' ? item.predicted_cpu_usage : item.predicted_ram_usage })) },
        ]} />
      </ChartPanel>
      <ChartPanel><TimeSeriesChart title="Future capacity & reservations" unit={resource === 'RAM' ? ' GB' : ' CPU'} series={[
        { name: 'Usable capacity', color: 'var(--muted)', dashed: true, points: future.map((item) => ({ time: item.window_start, value: currentUsable })) },
        { name: 'Predicted usage', color: 'var(--violet)', points: future.map((item) => ({ time: item.window_start, value: resource === 'CPU' ? item.predicted_cpu_usage : item.predicted_ram_usage })) },
        { name: 'Safe barterable', color: 'var(--green)', points: future.map((item) => ({ time: item.window_start, value: resource === 'CPU' ? item.safe_cpu_commitment : item.safe_ram_commitment })) },
        { name: 'Reserved', color: 'var(--amber)', dashed: true, points: future.map((item) => ({ time: item.window_start, value: resource === 'CPU' ? provider?.future_commitment_cpu ?? 0 : provider?.future_commitment_ram ?? 0 })) },
      ]} /></ChartPanel>
    </section>
  </div>
}
