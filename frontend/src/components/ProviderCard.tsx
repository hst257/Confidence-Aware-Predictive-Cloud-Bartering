import { PulseIcon, WarningIcon, CoinsIcon, CpuIcon, GaugeIcon, HardDrivesIcon, StackIcon, TrendDownIcon, TrendUpIcon, LightningIcon } from '@phosphor-icons/react'
import { Meter } from './Meter'
import type { Provider } from '../types'

export function ProviderCard({ provider, selected, onSelect, onDetails }: { provider: Provider; selected: boolean; onSelect: () => void; onDetails: () => void }) {
  const state = provider.current_state
  const prediction = provider.latest_prediction
  const cpuPercent = state ? state.cpu_usage / Math.max(state.usable_cpu, 1) * 100 : 0
  const ramPercent = state ? state.ram_usage / Math.max(state.usable_ram, 1) * 100 : 0
  const deficit = Boolean(prediction && (prediction.cpu_deficit > 0 || prediction.ram_deficit > 0))
  const impaired = provider.capacity_lost_cpu > 0 || provider.capacity_lost_ram > 0
  return <article id={`service-card-${provider.id}`} tabIndex={-1} aria-label={`${provider.name} detailed resources`} className={`provider-live-card panel ${selected ? 'selected' : ''} ${deficit || impaired ? 'at-risk' : ''}`} onClick={onSelect}>
    <div className="provider-head"><div className="provider-icon"><StackIcon size={19} /></div><div><h3><button type="button" className="provider-select-button" aria-pressed={selected} onClick={(event) => { event.stopPropagation(); onSelect() }}>{provider.name}</button></h3><span>{provider.personality}</span></div><i className={`health-dot ${deficit || impaired ? 'amber' : 'green'}`} /></div>
    {provider.active_event && <div className="active-event-chip"><LightningIcon size={12} /> {provider.active_event}</div>}
    <div className="util-pair">
      <div><span><CpuIcon size={13} /> CPU</span><strong>{cpuPercent.toFixed(1)}%</strong><Meter value={cpuPercent} total={100} tone={cpuPercent > 90 ? 'amber' : 'cyan'} /><small>{state?.cpu_available.toFixed(1) ?? '-'} available · {state?.usable_cpu.toFixed(0) ?? provider.total_cpu} usable</small></div>
      <div><span><HardDrivesIcon size={13} /> RAM</span><strong>{ramPercent.toFixed(1)}%</strong><Meter value={ramPercent} total={100} tone={ramPercent > 90 ? 'amber' : 'violet'} /><small>{state?.ram_available.toFixed(1) ?? '-'} GB available</small></div>
    </div>
    <div className={`forecast-strip ${deficit ? 'deficit' : 'surplus'}`}>
      {deficit ? <TrendDownIcon size={15} /> : <TrendUpIcon size={15} />}
      <span>{!prediction ? 'Awaiting first cycle' : deficit ? `${prediction.cpu_deficit.toFixed(1)} CPU deficit` : `${prediction.safe_cpu_commitment.toFixed(1)} safe CPU surplus`}</span>
      <strong>{prediction ? `${prediction.confidence}%` : '-'}</strong>
    </div>
    <div className="provider-metric-grid">
      <div><PulseIcon /><span>Volatility</span><strong>{provider.current_volatility.toFixed(2)}</strong></div>
      <div><WarningIcon /><span>Capacity lost</span><strong>{provider.capacity_lost_cpu.toFixed(0)} CPU</strong></div>
      <div><CoinsIcon /><span>Credits / collateral</span><strong>{provider.credit_balance.toFixed(0)} / {provider.locked_collateral.toFixed(1)}</strong></div>
      <div><GaugeIcon /><span>SLA / forecast</span><strong>{provider.sla_reputation.toFixed(0)} / {provider.forecast_reliability.toFixed(0)}</strong></div>
    </div>
    <button className="card-detail-button" onClick={(event) => { event.stopPropagation(); onDetails() }}>View details</button>
  </article>
}

