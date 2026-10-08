import { useEffect, useState } from 'react'
import { WarningOctagonIcon, BrainIcon, CloudSlashIcon, DiceFiveIcon, GaugeIcon, PauseIcon, PlayIcon, ArrowCounterClockwiseIcon, SkipForwardIcon, SparkleIcon, TrendDownIcon, LightningIcon } from '@phosphor-icons/react'
import type { Provider, SimulationConfiguration, SimulationState } from '../types'

export type ManualAction = 'generate' | 'match' | 'reevaluate' | 'startContracts' | 'completeContracts' | 'fail'
export type InjectKind = 'spike' | 'drop' | 'failure'

const manualControls: { action: ManualAction; label: string; icon: typeof SparkleIcon }[] = [
  { action: 'generate', label: 'Generate predictions', icon: SparkleIcon },
  { action: 'match', label: 'Run matching', icon: BrainIcon },
  { action: 'reevaluate', label: 'Re-evaluate', icon: GaugeIcon },
  { action: 'startContracts', label: 'Start contracts', icon: PlayIcon },
  { action: 'completeContracts', label: 'Complete contracts', icon: SkipForwardIcon },
  { action: 'fail', label: 'Simulate failure', icon: WarningOctagonIcon },
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
  const [providerId, setProviderId] = useState(providers[0]?.id ?? 0)
  const [severity, setSeverity] = useState<'info' | 'warning' | 'critical'>('warning')
  useEffect(() => {
    setScenario(simulation.scenario); setSeed(String(simulation.seed)); setRandomMode(simulation.random_mode)
  }, [simulation.run_id, simulation.scenario, simulation.seed, simulation.random_mode])
  useEffect(() => { if (!providers.some((item) => item.id === providerId)) setProviderId(providers[0]?.id ?? 0) }, [providers, providerId])
  const stress = simulation.scenario === 'Stress Test'
  return (
    <section className={`simulation-console panel ${simulation.running ? 'is-running' : ''} ${stress ? 'stress-mode' : ''}`} aria-live="polite">
      {stress && <div className="stress-banner"><WarningOctagonIcon size={14} /> <strong>Stress test active</strong><span>Elevated volatility, failures, and simultaneous shortages</span></div>}
      <div className="clock-block">
        <div className="simulation-state"><i /> Run #{simulation.run_id} · {simulation.running ? 'Running' : 'Paused'}</div>
        <div className="simulation-clock"><span>Day {simulation.day}</span><strong>{simulation.clock}</strong></div>
        <small>{simulation.scenario} · Seed {simulation.seed} · {simulation.mode} run</small>
      </div>
      <div className="transport-controls">
        <button className="transport primary" onClick={onToggle} disabled={busy}>
          {simulation.running ? <PauseIcon size={17} /> : <PlayIcon size={17} />}
          {simulation.running ? 'Pause' : simulation.clock === '08:00:00' ? 'Start' : 'Resume'}
        </button>
        <button className="transport" onClick={onStep} disabled={busy}><SkipForwardIcon size={17} /> Step +5m</button>
        <button className="transport quiet" onClick={onReset} disabled={busy}><ArrowCounterClockwiseIcon size={16} /> Reset run</button>
      </div>
      <div className="speed-control">
        <div className="speed-label"><span><GaugeIcon size={15} /> Simulated time speed</span><strong>{simulation.speed}×</strong></div>
        <input aria-label="Simulation speed" type="range" min="0" max={simulation.allowed_speeds.length - 1} step="1" value={speedIndex} onChange={(event) => onSpeed(simulation.allowed_speeds[Number(event.target.value)])} disabled={busy} />
        <div className="speed-ticks">{simulation.allowed_speeds.map((speedValue) => <span key={speedValue}>{speedValue}×</span>)}</div>
      </div>
      <div className="phase3-config">
        <label>Scenario<select aria-label="Simulation scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} disabled={busy || simulation.running}>{simulation.available_scenarios.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Randomness<select aria-label="Randomness mode" value={randomMode ? 'Random' : 'Reproducible'} onChange={(event) => setRandomMode(event.target.value === 'Random')} disabled={busy || simulation.running}><option>Reproducible</option><option>Random</option></select></label>
        <label>Seed<input aria-label="Random seed" type="number" min="1" max="2147483647" value={seed} onChange={(event) => setSeed(event.target.value)} disabled={busy || simulation.running || randomMode} /></label>
        <button className="config-action" onClick={() => onConfigure({ scenario, seed: randomMode ? null : Number(seed), random_mode: randomMode })} disabled={busy || simulation.running || (!randomMode && !Number(seed))}>Apply & restart</button>
        <button className="config-action" onClick={onRandomSeed} disabled={busy || simulation.running}><DiceFiveIcon size={14} /> Random seed</button>
        <button className="config-action" onClick={onRestartSameSeed} disabled={busy || simulation.running}><ArrowCounterClockwiseIcon size={14} /> Same seed</button>
      </div>
      <details className="manual-injection">
        <summary>Workload and failure injection</summary>
        <div className="injection-controls">
          <select aria-label="Injection provider" value={providerId} onChange={(event) => setProviderId(Number(event.target.value))}>{providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <select aria-label="Injection severity" value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="info">Low</option><option value="warning">Medium</option><option value="critical">High</option></select>
          <button onClick={() => onInject(providerId, 'spike', severity)} disabled={busy}><LightningIcon size={14} /> Traffic spike</button>
          <button onClick={() => onInject(providerId, 'failure', severity)} disabled={busy}><CloudSlashIcon size={14} /> Capacity failure</button>
          <button onClick={() => onInject(providerId, 'drop', severity)} disabled={busy}><TrendDownIcon size={14} /> Workload drop</button>
        </div>
      </details>
      <details className="manual-lab">
        <summary>Phase 1 manual lab</summary>
        <div>{manualControls.map(({ action, label, icon: Icon }) => <button key={action} onClick={() => onManual(action)} disabled={busy}><Icon size={14} /> {label}</button>)}</div>
      </details>
    </section>
  )
}
