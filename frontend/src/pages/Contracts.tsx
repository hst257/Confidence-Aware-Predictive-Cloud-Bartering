import { ArrowRight, Clock3, Coins, Cpu, Eye, GitBranch, HardDrive } from 'lucide-react'
import { StatusBadge } from '../components/StatusBadge'
import type { Contract, Renegotiation } from '../types'

export function Contracts({ contracts, renegotiations, onOpen }: { contracts: Contract[]; renegotiations: Renegotiation[]; onOpen: (id: number) => void }) {
  return (
    <div className="page-stack">
      {renegotiations.map((item) => (
        <div className="renegotiation-banner panel" key={item.id}><GitBranch /><div><strong>Contract #{item.original_contract_id} was proactively renegotiated</strong><span>{item.reason}. Replacement contracts: {item.replacement_contract_ids.map((id) => `#${id}`).join(', ')}.</span></div></div>
      ))}
      <section className="panel table-panel">
        <div className="panel-title-row"><div><span className="eyebrow">Future agreements</span><h2>Barter contracts</h2></div><span className="count-pill">{contracts.length} total</span></div>
        {contracts.length === 0 ? <div className="empty">No contracts created. Run matching and create the best suggested contract.</div> : (
          <div className="responsive-table"><table>
            <thead><tr><th>ID & route</th><th>Resources</th><th>Window</th><th>Economics</th><th>Confidence</th><th>Status</th><th /></tr></thead>
            <tbody>{contracts.map((c) => <tr key={c.id}>
              <td><strong>#{c.id} · {c.provider_name} <ArrowRight className="inline-icon" size={13} /> {c.consumer_name}</strong><small><span className={`barter-type ${c.barter_type.toLowerCase()}`}>{c.barter_type}</span> · {c.parent_contract_id ? `replacement for #${c.parent_contract_id}` : 'original agreement'}</small></td>
              <td><span className="table-icons"><Cpu size={14} /> {c.cpu_amount}</span><small><HardDrive size={13} /> {c.ram_amount} GB</small></td>
              <td><span className="table-icons"><Clock3 size={14} /> {new Date(c.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><small>to {new Date(c.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></td>
              <td><span className="table-icons"><Coins size={14} /> {c.barter_cost}</span><small>{c.collateral?.amount ?? 0} collateral · {c.collateral?.status ?? 'none'}</small></td>
              <td><strong>{c.prediction_confidence}%</strong><small>{c.match_score} match score</small></td>
              <td><StatusBadge status={c.status} /></td>
              <td><button className="icon-button" title="Open contract history" onClick={() => onOpen(c.id)}><Eye size={17} /></button></td>
            </tr>)}</tbody>
          </table></div>
        )}
      </section>
    </div>
  )
}
