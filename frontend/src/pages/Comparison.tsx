import { BarChart3, Sigma } from 'lucide-react'
import type { Snapshot } from '../types'

const metricLabel = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export function Comparison({ data }: { data: Snapshot }) {
  const comparison = data.experiment_comparison
  return <div className="page-stack">
    <section className="panel table-panel">
      <div className="panel-title-row"><div><span className="eyebrow">Same-seed strategy study</span><h2>Predictive vs reactive comparison</h2></div><BarChart3 /></div>
      <div className="responsive-table"><table><thead><tr><th>Run</th><th>Strategy</th><th>Seed</th><th>CPU utilization</th><th>Prevention</th><th>Emergencies</th><th>Unresolved</th><th>Renegotiated / failed</th><th>Collateral penalties</th><th>Contract success</th><th>Prediction / reaction lead time</th></tr></thead><tbody>{comparison.runs.map((run) => <tr key={run.run_id}><td><strong>#{run.run_id}</strong></td><td>{run.bartering_strategy}</td><td>{run.seed}</td><td>{run.total_cpu_utilization.toFixed(1)}%</td><td>{run.shortages_prevented}</td><td>{run.emergency_contracts}</td><td>{run.unresolved_shortages}</td><td>{run.renegotiations} / {run.failed_contracts}</td><td>{run.collateral_penalties.toFixed(1)}</td><td>{run.contract_success_rate.toFixed(1)}%</td><td>{run.average_prediction_lead_time.toFixed(1)}m / {run.average_reaction_time.toFixed(1)}m</td></tr>)}</tbody></table></div>
    </section>
    <section className="panel table-panel">
      <div className="panel-title-row"><div><span className="eyebrow">Descriptive statistics</span><h2>Strategy summary</h2></div><Sigma /></div>
      {comparison.strategy_summary.length === 0 ? <div className="empty">Complete or pause comparable runs to populate the statistical summary.</div> : <div className="responsive-table"><table><thead><tr><th>Strategy</th><th>Metric</th><th>Runs</th><th>Mean</th><th>Median</th><th>Minimum</th><th>Maximum</th><th>Std. deviation</th></tr></thead><tbody>{comparison.strategy_summary.flatMap((group) => comparison.metrics.map((metric) => <tr key={`${group.strategy}-${metric}`}><td><strong>{group.strategy}</strong></td><td>{metricLabel(metric)}</td><td>{group.run_count}</td><td>{group.metrics[metric].mean.toFixed(2)}</td><td>{group.metrics[metric].median.toFixed(2)}</td><td>{group.metrics[metric].min.toFixed(2)}</td><td>{group.metrics[metric].max.toFixed(2)}</td><td>{group.metrics[metric].stddev.toFixed(2)}</td></tr>))}</tbody></table></div>}
    </section>
  </div>
}
