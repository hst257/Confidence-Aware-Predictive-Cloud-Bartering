import { useEffect, useState } from 'react'
import { ChartPanel, DivergingBars, TimeSeriesChart, type ChartMarker } from '../components/Charts'
import { ProviderCard } from '../components/ProviderCard'
import type { Snapshot } from '../types'

function markersFor(data: Snapshot, providerId: number): ChartMarker[] {
  const stochastic: ChartMarker[] = data.stochastic_events.filter((event) => event.provider_id === providerId).map((event) => ({
    id: `s-${event.id}`, time: event.start_time,
    label: `${event.provider_name}: ${event.name} · ${event.affected_resource} ${event.event_type === 'workload_drop' ? '-' : '+'}${event.event_type === 'capacity_failure' ? event.capacity_loss_percent : event.magnitude_percent}%`,
    kind: event.event_type.replaceAll('_', ' '),
    color: event.event_type === 'capacity_failure' ? 'var(--red)' : event.event_type === 'workload_drop' ? 'var(--green)' : 'var(--amber)',
  }))
  const responses: ChartMarker[] = data.events.filter((event) => event.provider_id === providerId && /contract\.(created|at_risk|activated|renegotiated)|emergency\./.test(event.event_type)).map((event) => ({
    id: `e-${event.id}`, time: event.simulation_time ?? event.created_at, label: event.message,
    kind: event.event_type.replaceAll('.', ' '), color: event.event_type.includes('at_risk') ? 'var(--red)' : 'var(--cyan)',
  }))
  return [...stochastic, ...responses]
}

export function ServiceDetails({ data, selectedProviderId, onSelectProvider, onProviderDetails, rangeMinutes, onRangeChange, focusProviderId }: {
  data: Snapshot; selectedProviderId: number; onSelectProvider: (id: number) => void; onProviderDetails: (id: number) => void
  rangeMinutes: number; onRangeChange: (minutes: number) => void; focusProviderId: number | null
}) {
  useEffect(() => {
    if (focusProviderId === null) return
    const card = document.getElementById(`service-card-${focusProviderId}`)
    card?.focus({ preventScroll: true })
    card?.scrollIntoView({ block: 'start' })
  }, [focusProviderId])
  const [resource, setResource] = useState<'CPU' | 'RAM'>('CPU')
  const selected = data.selected_provider?.provider.id === selectedProviderId ? data.selected_provider : null
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
    <div className="section-heading"><div><span className="eyebrow">Live stochastic federation</span><h2>All service resources</h2></div><span className="updated">Select a service for telemetry, or open its full audit</span></div>
    <section className="provider-live-grid" aria-label="Detailed service resources">{data.providers.map((item) => <ProviderCard key={item.id} provider={item} selected={item.id === selectedProviderId} onSelect={() => onSelectProvider(item.id)} onDetails={() => onProviderDetails(item.id)} />)}</section>

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

