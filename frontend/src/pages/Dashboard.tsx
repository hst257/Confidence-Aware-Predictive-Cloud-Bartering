import { ArrowUpRightIcon, PulseIcon, BrainIcon, CheckCircleIcon, CpuIcon, HardDrivesIcon, HeartbeatIcon, StackIcon, ShieldCheckIcon, SirenIcon, LightningIcon } from '@phosphor-icons/react'
import { ChartPanel, DivergingBars } from '../components/Charts'
import { Meter } from '../components/Meter'
import type { Provider, Snapshot } from '../types'

function ServiceRow({ provider, onOpen }: { provider: Provider; onOpen: () => void }) {
  const state = provider.current_state
  const prediction = provider.latest_prediction
  const cpuPercent = state ? state.cpu_usage / Math.max(state.usable_cpu, 1) * 100 : 0
  const ramPercent = state ? state.ram_usage / Math.max(state.usable_ram, 1) * 100 : 0
  const shortage = Boolean(state && (state.cpu_usage > state.usable_cpu || state.ram_usage > state.usable_ram))
  const impaired = provider.capacity_lost_cpu > 0 || provider.capacity_lost_ram > 0
  const forecastRisk = Boolean(prediction && (prediction.cpu_deficit > 0 || prediction.ram_deficit > 0))
  const status = !state ? 'Waiting' : shortage ? 'Shortage' : impaired ? 'Degraded' : forecastRisk ? 'Forecast risk' : provider.active_event ? 'Event active' : 'Healthy'
  const tone = shortage ? 'negative' : impaired || forecastRisk || provider.active_event ? 'warning-text' : 'positive'
  const forecast = !prediction ? 'Awaiting forecast' : forecastRisk
    ? prediction.cpu_deficit > 0 ? `${prediction.cpu_deficit.toFixed(1)} CPU deficit` : `${prediction.ram_deficit.toFixed(1)} GB deficit`
    : `${prediction.safe_cpu_commitment.toFixed(1)} safe CPU`
  return <button type="button" className="service-row" onClick={onOpen} aria-label={`View ${provider.name} in Service details`}>
    <span className="service-identity"><span className="provider-icon"><StackIcon size={18} /></span><span><strong>{provider.name}</strong><small>{provider.personality}</small></span></span>
    <span className={`service-status ${tone}`}><i />{status}</span>
    <span className="service-resource"><span><CpuIcon size={12} /> CPU <strong>{state ? `${cpuPercent.toFixed(1)}%` : '—'}</strong></span><Meter inline value={cpuPercent} total={100} tone={cpuPercent > 90 ? 'amber' : 'cyan'} /></span>
    <span className="service-resource"><span><HardDrivesIcon size={12} /> RAM <strong>{state ? `${ramPercent.toFixed(1)}%` : '—'}</strong></span><Meter inline value={ramPercent} total={100} tone={ramPercent > 90 ? 'amber' : 'violet'} /></span>
    <span className="service-forecast"><strong className={forecastRisk ? 'warning-text' : ''}>{forecast}</strong><small>{prediction ? `${prediction.confidence.toFixed(0)}% confidence` : 'First cycle pending'}</small></span>
    <ArrowUpRightIcon size={16} className="service-open-icon" />
  </button>
}

export function Dashboard({ data, onProviderDetails }: { data: Snapshot; onProviderDetails: (id: number) => void }) {
  const position = data.providers.map((provider) => {
    const prediction = provider.latest_prediction
    return { name: provider.name, value: prediction ? prediction.cpu_deficit ? -prediction.cpu_deficit : prediction.safe_cpu_commitment : 0 }
  })
  return <div className="page-stack">
    <section className="phase3-status-grid">
      <div className="kpi"><LightningIcon /><div><span>Active events</span><strong>{data.analytics.active_events}</strong><small>{data.analytics.active_failures} capacity failures</small></div></div>
      <div className="kpi"><ShieldCheckIcon /><div><span>Contract posture</span><strong>{data.analytics.active_contracts} active</strong><small>{data.analytics.at_risk_contracts} at risk · {data.analytics.predictive_contracts} predictive</small></div></div>
      <div className="kpi"><BrainIcon /><div><span>Forecast demand</span><strong>{data.analytics.predicted_deficits}</strong><small>{data.analytics.current_emergencies} current emergencies</small></div></div>
      <div className="kpi"><CheckCircleIcon /><div><span>Shortages prevented</span><strong>{data.analytics.shortages_prevented}</strong><small>{data.analytics.emergency_recoveries} emergency recoveries</small></div></div>
      <div className="kpi"><SirenIcon /><div><span>Unresolved shortages</span><strong>{data.analytics.unresolved_shortages}</strong><small>{data.analytics.average_reaction_time.toFixed(1)} min average reaction</small></div></div>
      <div className="kpi"><HeartbeatIcon /><div><span>System resilience</span><strong>{data.analytics.system_resilience_score.toFixed(1)}</strong><small>Project-specific simulation score</small></div></div>
      <div className="kpi"><PulseIcon /><div><span>Federation utilization</span><strong>{data.analytics.total_cpu_utilization.toFixed(1)}%</strong><small>{data.analytics.total_ram_utilization.toFixed(1)}% usable RAM</small></div></div>
      <div className="kpi"><BrainIcon /><div><span>Forecast accuracy</span><strong>{data.analytics.average_forecast_accuracy ? `${data.analytics.average_forecast_accuracy.toFixed(1)}%` : 'Learning'}</strong><small>{data.analytics.forecast_metrics.reduce((sum, item) => sum + item.predictions_evaluated, 0)} evaluated</small></div></div>
    </section>
    <div className="section-heading"><div><span className="eyebrow">Live stochastic federation</span><h2>Services at a glance <span className="count-pill">{data.providers.length}</span></h2></div><span className="updated">Select a service to open its detailed resources</span></div>
    <section className="service-list panel" aria-label="Live services">
      {data.providers.map((provider) => <ServiceRow key={provider.id} provider={provider} onOpen={() => onProviderDetails(provider.id)} />)}
    </section>
    <ChartPanel><DivergingBars title="Predicted federation position" values={position} /></ChartPanel>
  </div>
}
