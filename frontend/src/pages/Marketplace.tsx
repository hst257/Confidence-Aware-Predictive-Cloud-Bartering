import { ArrowRight, BrainCircuit, Check, Coins, Cpu, HardDrive, ShieldCheck } from 'lucide-react'
import type { Match, Prediction } from '../types'

export function Marketplace({ matches, predictions, onCreate, busy }: { matches: Match[]; predictions: Prediction[]; onCreate: (match: Match) => void; busy: boolean }) {
  const needs = predictions.filter((p) => p.cpu_deficit || p.ram_deficit)
  const offers = predictions.filter((p) => p.predicted_cpu_spare || p.predicted_ram_spare)
  return (
    <div className="page-stack">
      <section className="market-overview">
        <div className="panel market-side demand-side"><span className="eyebrow">Demand</span><h2>Resources required</h2>{needs.length ? needs.map((p) => <div className="market-row" key={p.id}><strong>{p.provider_name}</strong><span>{p.cpu_deficit} CPU · {p.ram_deficit} GB</span></div>) : <div className="empty compact">No predicted deficits.</div>}</div>
        <div className="market-arrow"><ArrowRight /></div>
        <div className="panel market-side offer-side"><span className="eyebrow">Supply</span><h2>Predicted offers</h2>{offers.length ? offers.map((p) => <div className="market-row" key={p.id}><strong>{p.provider_name}</strong><span>{p.predicted_cpu_spare} CPU · {p.predicted_ram_spare} GB</span></div>) : <div className="empty compact">No predicted surplus.</div>}</div>
      </section>
      <section>
        <div className="section-heading"><div><span className="eyebrow">Confidence-aware ranking</span><h2>Suggested matches</h2></div><span className="updated">Weighted policy score</span></div>
        {matches.length === 0 ? <div className="panel empty">Generate predictions and run matching to see ranked contracts.</div> : (
          <div className="match-grid">
            {matches.map((match, index) => (
              <article className={`panel match-card ${index === 0 ? 'best' : ''}`} key={`${match.provider_id}-${match.consumer_id}`}>
                {index === 0 && <span className="best-label"><Check size={13} /> Best match</span>}
                <div className="match-route"><div><small>Provider</small><strong>{match.provider_name}</strong></div><ArrowRight /><div><small>Consumer</small><strong>{match.consumer_name}</strong></div><span className="match-score">{match.match_score}<small>/100</small></span></div>
                <div className="match-resources"><span><Cpu size={16} /> {match.cpu_amount} CPU</span><span><HardDrive size={16} /> {match.ram_amount} GB</span><span><Coins size={16} /> {match.barter_cost} credits</span><span><ShieldCheck size={16} /> {match.collateral} collateral</span></div>
                <div className="reason"><BrainCircuit size={17} /><p>{match.selection_reason}</p></div>
                <div className="match-footer"><span>{match.confidence}% confidence · {match.forecast_reliability}% reliable</span><button className="primary small" onClick={() => onCreate(match)} disabled={busy}>Create contract</button></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
