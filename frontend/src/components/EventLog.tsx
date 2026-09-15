import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleDot, Filter } from 'lucide-react'
import type { Provider, SystemEvent } from '../types'

const icon = { info: CircleDot, warning: AlertTriangle, error: AlertTriangle }

function simulationLabel(value: string | null, fallback: string) {
  const date = new Date(value ?? fallback)
  const day = Math.max(1, Math.floor((date.getTime() - new Date('2026-01-01T00:00:00').getTime()) / 86400000) + 1)
  return value ? `Day ${day} · ${date.toLocaleTimeString([], { hour12: false })}` : date.toLocaleTimeString([], { hour12: false })
}

export function EventLog({ events, providers }: { events: SystemEvent[]; providers: Provider[] }) {
  const [provider, setProvider] = useState('all')
  const [severity, setSeverity] = useState('all')
  const [type, setType] = useState('all')
  const [contract, setContract] = useState('all')
  const types = useMemo(() => [...new Set(events.map((event) => event.event_type.split('.')[0]))], [events])
  const contracts = useMemo(() => [...new Set(events.flatMap((event) => event.contract_id ? [event.contract_id] : []))], [events])
  const filtered = events.filter((event) =>
    (provider === 'all' || event.provider_id === Number(provider))
    && (severity === 'all' || event.severity === severity)
    && (type === 'all' || event.event_type.startsWith(`${type}.`))
    && (contract === 'all' || event.contract_id === Number(contract)),
  )
  return <aside className="event-panel panel">
    <div className="panel-title-row"><div><span className="eyebrow">Simulation history</span><h2>Event timeline</h2></div><span className="live-indicator"><i /> Live</span></div>
    <div className="event-filters">
      <Filter size={13} />
      <select aria-label="Filter events by provider" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">All providers</option>{providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      <select aria-label="Filter events by type" value={type} onChange={(event) => setType(event.target.value)}><option value="all">All events</option>{types.map((item) => <option key={item} value={item}>{item}</option>)}</select>
      <select aria-label="Filter events by contract" value={contract} onChange={(event) => setContract(event.target.value)}><option value="all">All contracts</option>{contracts.map((item) => <option key={item} value={item}>Contract #{item}</option>)}</select>
      <select aria-label="Filter events by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">All severity</option><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option></select>
    </div>
    <div className="event-list">
      {filtered.length === 0 && <div className="empty compact">No events match these filters.</div>}
      {filtered.map((event, index) => {
        const Icon = event.event_type === 'contract.completed' ? CheckCircle2 : icon[event.severity]
        return <div className={`event event-${event.severity}`} key={event.id}>
          <div className="event-rail"><Icon size={15} />{index < filtered.length - 1 && <span />}</div>
          <div><time>{simulationLabel(event.simulation_time, event.created_at)}</time><p>{event.message}</p><small>{event.event_type.replaceAll('.', ' · ')}</small></div>
        </div>
      })}
    </div>
  </aside>
}
