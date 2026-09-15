import { useEffect, useState } from 'react'
import { AlertOctagon, BrainCircuit, CloudOff, Dice5, Gauge, Pause, Play, RotateCcw, SkipForward, Sparkles, TrendingDown, Zap } from 'lucide-react'
import type { Provider, SimulationConfiguration, SimulationState } from '../types'

export type ManualAction = 'generate' | 'match' | 'reevaluate' | 'startContracts' | 'completeContracts' | 'fail'
export type InjectKind = 'spike' | 'drop' | 'failure'

const manualControls: { action: ManualAction; label: string; icon: typeof Sparkles }[] = [
  { action: 'generate', label: 'Generate predictions', icon: Sparkles },
  { action: 'match', label: 'Run matching', icon: BrainCircuit },
  { action: 'reevaluate', label: 'Re-evaluate', icon: Gauge },
  { action: 'startContracts', label: 'Start contracts', icon: Play },
  { action: 'completeContracts', label: 'Complete contracts', icon: SkipForward },
  { action: 'fail', label: 'Simulate failure', icon: AlertOctagon },
]

export function SimulationControls({
  simulation, providers, busy, onToggle, onReset, onStep, onSpeed, onManual,
  onConfigure, onRandomSeed, onRestartSameSeed, onInject,
}: {
  simulation: SimulationState
  providers: Provider[]
  busy: boolean
  onToggle: () => void
  onReset: () => void
  onStep: () => void
  onSpeed: (speed: number) => void
  onManual: (action: ManualAction) => void
  onConfigure: (configuration: SimulationConfiguration) => void
  onRandomSeed: () => void
  onRestartSameSeed: () => void
  onInject: (providerId: number, kind: InjectKind, severity: 'info' | 'warning' | 'critical') => void
}) {
  const speedIndex = Math.max(0, simulation.allowed_speeds.indexOf(simulation.speed))
  const [scenario, setScenario] = useState(simulation.scenario)
  const [seed, setSeed] = useState(String(simulation.seed))
  const [randomMode, setRandomMode] = useState(simulation.random_mode)
  const [forecastModel, setForecastModel] = useState(simulation.forecast_model)
  const [shadowModels, setShadowModels] = useState(simulation.shadow_models)
  const [trainingWindow, setTrainingWindow] = useState(simulation.training_window_minutes)
  const [strategy, setStrategy] = useState(simulation.bartering_strategy)
  const [safetyMargin, setSafetyMargin] = useState(simulation.safety_margin_multiplier)
  const [selectionPeriod, setSelectionPeriod] = useState(simulation.model_selection_period_minutes)
  const [providerId, setProviderId] = useState(providers[0]?.id ?? 0)
  const [severity, setSeverity] = useState<'info' | 'warning' | 'critical'>('warning')
  useEffect(() => {
    setScenario(simulation.scenario); setSeed(String(simulation.seed)); setRandomMode(simulation.random_mode)
    setForecastModel(simulation.forecast_model); setShadowModels(simulation.shadow_models)
    setTrainingWindow(simulation.training_window_minutes); setStrategy(simulation.bartering_strategy)
    setSafetyMargin(simulation.safety_margin_multiplier); setSelectionPeriod(simulation.model_selection_period_minutes)
  }, [simulation.run_id, simulation.scenario, simulation.seed, simulation.random_mode, simulation.forecast_model, simulation.shadow_models, simulation.training_window_minutes, simulation.bartering_strategy, simulation.safety_margin_multiplier, simulation.model_selection_period_minutes])
  useEffect(() => { if (!providers.some((item) => item.id === providerId)) setProviderId(providers[0]?.id ?? 0) }, [providers, providerId])
  const stress = simulation.scenario === 'Stress Test'
  return (
    <section className={`simulation-console panel ${simulation.running ? 'is-running' : ''} ${stress ? 'stress-mode' : ''}`} aria-live="polite">
      {stress && <div className="stress-banner"><AlertOctagon size={14} /> STRESS TEST ACTIVE · elevated volatility, failures, and simultaneous shortages</div>}
      <div className="clock-block">
        <div className="simulation-state"><i /> RUN #{simulation.run_id} · {simulation.running ? 'RUNNING' : 'PAUSED'}</div>
        <div className="simulation-clock"><span>Day {simulation.day}</span><strong>{simulation.clock}</strong></div>
        <small>{simulation.scenario} · Seed {simulation.seed} · {simulation.forecast_model} · {simulation.bartering_strategy}</small>
      </div>
      <div className="transport-controls">
        <button className="transport primary" onClick={onToggle} disabled={busy}>
          {simulation.running ? <Pause size={17} /> : <Play size={17} />}
          {simulation.running ? 'Pause' : simulation.clock === '08:00:00' ? 'Start' : 'Resume'}
        </button>
        <button className="transport" onClick={onStep} disabled={busy}><SkipForward size={17} /> Step +5m</button>
        <button className="transport quiet" onClick={onReset} disabled={busy}><RotateCcw size={16} /> Reset run</button>
      </div>
      <div className="speed-control">
        <div className="speed-label"><span><Gauge size={15} /> Simulated time speed</span><strong>{simulation.speed}×</strong></div>
        <input aria-label="Simulation speed" type="range" min="0" max={simulation.allowed_speeds.length - 1} step="1" value={speedIndex} onChange={(event) => onSpeed(simulation.allowed_speeds[Number(event.target.value)])} disabled={busy} />
        <div className="speed-ticks">{simulation.allowed_speeds.map((speedValue) => <span key={speedValue}>{speedValue}×</span>)}</div>
      </div>
      <div className="phase3-config">
        <label>Scenario<select aria-label="Simulation scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={busy || simulation.running}>{simulation.available_scenarios.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Randomness<select aria-label="Randomness mode" value={randomMode ? 'Random' : 'Reproducible'} onChange={(event) => setRandomMode(event.target.value === 'Random')} disabled={busy || simulation.running}><option>Reproducible</option><option>Random</option></select></label>
        <label>Seed<input aria-label="Random seed" type="number" min="1" max="2147483647" value={seed} onChange={(event) => setSeed(event.target.value)} disabled={busy || simulation.running || randomMode} /></label>
        <button className="config-action" onClick={() => onConfigure({ scenario, seed: randomMode ? null : Number(seed), random_mode: randomMode, forecast_model: forecastModel, shadow_models: shadowModels, training_window_minutes: trainingWindow, bartering_strategy: strategy, safety_margin_multiplier: safetyMargin, model_selection_period_minutes: selectionPeriod })} disabled={busy || simulation.running || (!randomMode && !Number(seed))}>Apply & restart</button>
        <button className="config-action" onClick={onRandomSeed} disabled={busy || simulation.running}><Dice5 size={14} /> Random seed</button>
        <button className="config-action" onClick={onRestartSameSeed} disabled={busy || simulation.running}><RotateCcw size={14} /> Same seed</button>
      </div>
      <div className="phase4-config">
        <label>Decision model<select value={forecastModel} onChange={(event) => setForecastModel(event.target.value)} disabled={busy || simulation.running}>{simulation.available_models.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Training window<select value={trainingWindow} onChange={(event) => setTrainingWindow(Number(event.target.value))} disabled={busy || simulation.running}>{simulation.available_training_windows.map((item) => <option value={item} key={item}>{item < 1440 ? `${item / 60} hours` : `${item / 1440} ${item === 1440 ? 'day' : 'days'}`}</option>)}</select></label>
        <label>Bartering strategy<select value={strategy} onChange={(event) => setStrategy(event.target.value as typeof strategy)} disabled={busy || simulation.running}>{simulation.available_strategies.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Uncertainty margin<input type="number" min="0.25" max="3" step="0.25" value={safetyMargin} onChange={(event) => setSafetyMargin(Number(event.target.value))} disabled={busy || simulation.running} /></label>
        <label>Model refresh<select value={selectionPeriod} onChange={(event) => setSelectionPeriod(Number(event.target.value))} disabled={busy || simulation.running}><option value={30}>30 min</option><option value={60}>60 min</option><option value={120}>2 hours</option><option value={360}>6 hours</option></select></label>
        <details className="shadow-models"><summary>Shadow models ({shadowModels.length})</summary><div>{simulation.available_models.filter((item) => item !== 'Auto').map((item) => <label key={item}><input type="checkbox" checked={shadowModels.includes(item)} onChange={(event) => setShadowModels(event.target.checked ? [...shadowModels, item] : shadowModels.filter((value) => value !== item))} disabled={busy || simulation.running} /> {item}</label>)}</div></details>
      </div>
      <details className="manual-injection">
        <summary>Workload and failure injection</summary>
        <div className="injection-controls">
          <select aria-label="Injection provider" value={providerId} onChange={(event) => setProviderId(Number(event.target.value))}>{providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <select aria-label="Injection severity" value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="info">Low</option><option value="warning">Medium</option><option value="critical">High</option></select>
          <button onClick={() => onInject(providerId, 'spike', severity)} disabled={busy}><Zap size={14} /> Traffic spike</button>
          <button onClick={() => onInject(providerId, 'failure', severity)} disabled={busy}><CloudOff size={14} /> Capacity failure</button>
          <button onClick={() => onInject(providerId, 'drop', severity)} disabled={busy}><TrendingDown size={14} /> Workload drop</button>
        </div>
      </details>
      <details className="manual-lab">
        <summary>Phase 1 manual lab</summary>
        <div>{manualControls.map(({ action, label, icon: Icon }) => <button key={action} onClick={() => onManual(action)} disabled={busy}><Icon size={14} /> {label}</button>)}</div>
      </details>
    </section>
  )
}
