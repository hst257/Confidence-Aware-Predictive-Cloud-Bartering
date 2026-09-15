import { ArrowDownRight, ArrowUpRight, CalendarClock, ShieldCheck } from 'lucide-react'
import type { Prediction } from '../types'

export function Predictions({ predictions }: { predictions: Prediction[] }) {
  return (
    <section className="panel table-panel">
      <div className="panel-title-row">
        <div><span className="eyebrow">Forward capacity</span><h2>Upcoming predictions</h2></div>
        {predictions[0] && <span className="window"><CalendarClock size={15} /> {new Date(predictions[0].window_start).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}–{new Date(predictions[0].window_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
      </div>
      {predictions.length === 0 ? <div className="empty">No predictions yet. Use “Generate predictions” to create the demo forecast window.</div> : (
        <div className="responsive-table">
          <table>
            <thead><tr><th>Provider</th><th>Horizon</th><th>Type</th><th>Predicted use</th><th>Predicted spare</th><th>Safe commitment</th><th>Confidence</th><th>Window</th></tr></thead>
            <tbody>
              {predictions.map((p) => {
                const deficit = p.cpu_deficit > 0 || p.ram_deficit > 0
                return (
                  <tr key={p.id}>
                    <td><strong>{p.provider_name}</strong><small>Prediction #{p.id}</small></td>
                    <td><strong>+{p.horizon_minutes || 'manual'}{p.horizon_minutes ? 'm' : ''}</strong><small>{new Date(p.window_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></td>
                    <td><span className={`direction ${deficit ? 'deficit' : 'surplus'}`}>{deficit ? <ArrowDownRight size={15} /> : <ArrowUpRight size={15} />}{deficit ? 'Deficit' : 'Surplus'}</span></td>
                    <td>{p.predicted_cpu_usage} CPU<small>{p.predicted_ram_usage} GB RAM</small></td>
                    <td>{p.predicted_cpu_spare} CPU<small>{p.predicted_ram_spare} GB RAM</small></td>
                    <td>{p.safe_cpu_commitment} CPU<small>{p.safe_ram_commitment} GB RAM</small></td>
                    <td><div className="score-inline"><ShieldCheck size={15} /><strong>{p.confidence}%</strong></div></td>
                    <td><span className={`kind kind-${p.kind.toLowerCase()}`}>{p.kind}</span><small>{new Date(p.window_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} end</small></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
