import { Award, BrainCircuit, Coins, History, ShieldCheck, Trophy } from 'lucide-react'
import type { CreditTransaction, Provider, ReputationHistory } from '../types'

export function Reputation({ providers, history, transactions }: { providers: Provider[]; history: ReputationHistory[]; transactions: CreditTransaction[] }) {
  return (
    <div className="page-stack">
      <section className="reputation-grid">
        {providers.map((p, index) => <article className="panel reputation-card" key={p.id}>
          <div className="reputation-head"><div className="rank">{index + 1}</div><div><h3>{p.name}</h3><span>{p.successful_contracts} successful · {p.failed_predictions} failed</span></div>{index === 0 && <Trophy size={19} />}</div>
          <div className="score-row"><span><ShieldCheck size={15} /> SLA reputation</span><strong>{p.sla_reputation.toFixed(1)}</strong></div>
          <div className="score-row"><span><BrainCircuit size={15} /> Forecast reliability</span><strong>{p.forecast_reliability.toFixed(1)}</strong></div>
          <div className="score-row"><span><Award size={15} /> Contribution score</span><strong>{p.contribution_score.toFixed(1)}</strong></div>
          <div className="score-row credits"><span><Coins size={15} /> Barter balance</span><strong>{p.credit_balance.toFixed(1)}</strong></div>
        </article>)}
      </section>
      <section className="dual-panels">
        <div className="panel activity-panel"><div className="panel-title-row"><div><span className="eyebrow">Measured outcomes</span><h2>Reputation changes</h2></div><History size={18} /></div>{history.length === 0 ? <div className="empty compact">Scores update when a contract settles or fails.</div> : history.slice(0, 12).map((h) => <div className="history-row" key={h.id}><div><strong>{h.provider_name}</strong><span>{h.metric} · Contract #{h.contract_id}</span></div><span className={h.new_value >= h.old_value ? 'positive' : 'negative'}>{h.old_value} → {h.new_value}</span></div>)}</div>
        <div className="panel activity-panel"><div className="panel-title-row"><div><span className="eyebrow">Auditable economics</span><h2>Credit ledger</h2></div><Coins size={18} /></div>{transactions.length === 0 ? <div className="empty compact">Collateral and settlement transactions appear here.</div> : transactions.slice(0, 12).map((t) => <div className="history-row" key={t.id}><div><strong>{t.provider_name}</strong><span>{t.transaction_type} · Contract #{t.contract_id}</span></div><span className={t.amount >= 0 ? 'positive' : 'negative'}>{t.amount > 0 ? '+' : ''}{t.amount.toFixed(2)}</span></div>)}</div>
      </section>
    </div>
  )
}
