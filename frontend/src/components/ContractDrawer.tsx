import { ArrowRightIcon, CoinsIcon, ClockCounterClockwiseIcon, XIcon } from '@phosphor-icons/react'
import { StatusBadge } from './StatusBadge'
import type { Contract, CreditTransaction, ReputationHistory, SystemEvent } from '../types'

type Detail = { contract: Contract; transactions: CreditTransaction[]; reputation_history: ReputationHistory[]; events: SystemEvent[] }

export function ContractDrawer({ detail, onClose }: { detail: Detail | null; onClose: () => void }) {
  if (!detail) return null
  const { contract } = detail
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="drawer" onMouseDown={(e) => e.stopPropagation()}>
    <div className="drawer-head"><div><span className="eyebrow">Agreement audit</span><h2>Contract #{contract.id}</h2></div><button className="icon-button" onClick={onClose}><XIcon /></button></div>
    <div className="drawer-route"><strong>{contract.provider_name}</strong><ArrowRightIcon /><strong>{contract.consumer_name}</strong><StatusBadge status={contract.status} /></div>
    <div className="detail-grid"><div><span>CPU</span><strong>{contract.cpu_amount}</strong></div><div><span>RAM</span><strong>{contract.ram_amount} GB</strong></div><div><span>Cost</span><strong>{contract.barter_cost}</strong></div><div><span>Collateral</span><strong>{contract.collateral?.amount ?? 0}</strong></div></div>
    <div className="reason drawer-reason"><p>{contract.selection_reason}</p></div>
    <div className="drawer-section"><h3><CoinsIcon size={16} /> Credit & collateral history</h3>{detail.transactions.length ? detail.transactions.map((t) => <div className="drawer-row" key={t.id}><span>{t.description}</span><strong className={t.amount >= 0 ? 'positive' : 'negative'}>{t.amount > 0 ? '+' : ''}{t.amount}</strong></div>) : <div className="empty compact">No ledger entries.</div>}</div>
    <div className="drawer-section"><h3><ClockCounterClockwiseIcon size={16} /> Contract timeline</h3>{detail.events.map((e) => <div className="drawer-event" key={e.id}><time>{new Date(e.created_at).toLocaleTimeString()}</time><span>{e.message}</span></div>)}</div>
    {detail.reputation_history.length > 0 && <div className="drawer-section"><h3>Settlement measurements</h3>{detail.reputation_history.map((h) => <div className="drawer-row" key={h.id}><span>{h.metric}{h.forecast_accuracy !== null ? ` · ${h.forecast_accuracy}% accuracy` : ''}</span><strong>{h.old_value} → {h.new_value}</strong></div>)}</div>}
  </aside></div>
}
