import { Download, FlaskConical, Repeat2 } from 'lucide-react'
import { experimentExportUrl } from '../api'
import type { Snapshot } from '../types'

export function Experiments({ data }: { data: Snapshot }) {
  return <div className="page-stack">
    <section className="run-summary panel">
      <div><span className="eyebrow">Experiment configuration</span><h2>Run #{data.simulation.run_id} · seed {data.simulation.seed}</h2><p>Use the controls above to keep the same seed and switch strategies for a fair comparison.</p></div>
      <div><strong>{data.simulation.forecast_model}</strong><span>Decision model</span><small>{data.simulation.shadow_models.length} shadow models</small></div>
      <div><strong>{data.simulation.training_window_minutes / 60}h</strong><span>Training window</span><small>{data.simulation.model_selection_period_minutes}m selection cycle</small></div>
      <div><strong>{data.simulation.safety_margin_multiplier.toFixed(2)}×</strong><span>Safety margin</span><small>{data.simulation.bartering_strategy}</small></div>
    </section>
    <section className="analysis-kpis">
      <div className="analysis-kpi panel"><FlaskConical /><span>Current strategy</span><strong>{data.simulation.bartering_strategy}</strong><small>Persisted with this run</small></div>
      <div className="analysis-kpi panel"><Repeat2 /><span>Reproducibility key</span><strong>{data.simulation.seed}</strong><small>{data.simulation.scenario} scenario</small></div>
      <div className="analysis-kpi panel"><Download /><span>Portable results</span><strong>{data.experiment_comparison.runs.length}</strong><small>saved experiment runs</small></div>
    </section>
    <section className="panel table-panel">
      <div className="panel-title-row"><div><span className="eyebrow">Reproducible run matrix</span><h2>Experiment history</h2></div><div className="export-actions"><a href={experimentExportUrl('csv')}>Export CSV</a><a href={experimentExportUrl('json')}>Export JSON</a></div></div>
      <div className="responsive-table"><table><thead><tr><th>Run</th><th>Seed / scenario</th><th>Strategy</th><th>Model</th><th>Window</th><th>Duration</th><th>Prevented</th><th>Emergencies</th><th>Unresolved</th><th>Accuracy</th><th>Resilience</th></tr></thead><tbody>{data.experiment_comparison.runs.map((run) => <tr key={run.run_id}><td><strong>#{run.run_id}</strong><small>{run.status}</small></td><td>{run.seed}<small>{run.scenario}</small></td><td>{run.bartering_strategy}</td><td>{run.forecast_model}</td><td>{run.training_window_minutes / 60}h</td><td>{run.duration_minutes.toFixed(0)}m</td><td>{run.shortages_prevented}</td><td>{run.emergency_contracts}</td><td>{run.unresolved_shortages}</td><td>{run.average_forecast_accuracy.toFixed(1)}%</td><td>{run.system_resilience_score.toFixed(1)}</td></tr>)}</tbody></table></div>
    </section>
  </div>
}
