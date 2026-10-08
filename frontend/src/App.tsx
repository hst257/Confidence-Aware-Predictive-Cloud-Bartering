import { useCallback, useEffect, useRef, useState } from 'react'
import { PulseIcon, ChartBarIcon, BrainIcon, CloudIcon, FileTextIcon, SquaresFourIcon, ListIcon, ArrowsClockwiseIcon, ShieldCheckIcon, XIcon } from '@phosphor-icons/react'
import { actions, loadSnapshot } from './api'
import { ContractDrawer } from './components/ContractDrawer'
import { EventLog } from './components/EventLog'
import { SimulationControls, type InjectKind, type ManualAction } from './components/SimulationControls'
import { Analytics } from './pages/Analytics'
import { Contracts } from './pages/Contracts'
import { Dashboard } from './pages/Dashboard'
import { Marketplace } from './pages/Marketplace'
import { Predictions } from './pages/Predictions'
import { ProviderDetail } from './pages/ProviderDetail'
import { Reputation } from './pages/Reputation'
import type { Match, Snapshot } from './types'

type Page = 'overview' | 'predictions' | 'marketplace' | 'contracts' | 'reputation' | 'analytics' | 'provider'
type ContractDetail = Parameters<typeof ContractDrawer>[0]['detail']

const nav: { id: Exclude<Page, 'provider'>; label: string; icon: typeof SquaresFourIcon }[] = [
  { id: 'overview', label: 'Live overview', icon: SquaresFourIcon },
  { id: 'predictions', label: 'Predictions', icon: BrainIcon },
  { id: 'marketplace', label: 'Marketplace', icon: ChartBarIcon },
  { id: 'contracts', label: 'Contracts', icon: FileTextIcon },
  { id: 'reputation', label: 'Reputation', icon: ShieldCheckIcon },
  { id: 'analytics', label: 'Analytics', icon: PulseIcon },
]

function App() {
  const [page, setPage] = useState<Page>('overview')
  const [data, setData] = useState<Snapshot | null>(null)
  const [selectedProviderId, setSelectedProviderId] = useState(1)
  const [rangeMinutes, setRangeMinutes] = useState(360)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<ContractDetail>(null)
  const [mobileNav, setMobileNav] = useState(false)
  const refreshing = useRef(false)

  const refresh = useCallback(async (quiet = false) => {
    if (refreshing.current) return
    refreshing.current = true
    try {
      const snapshot = await loadSnapshot(selectedProviderId, rangeMinutes)
      setData(snapshot)
      if (snapshot.selected_provider && snapshot.selected_provider.provider.id !== selectedProviderId) {
        setSelectedProviderId(snapshot.selected_provider.provider.id)
      }
      setError(null)
    } catch (err) {
      if (!quiet) setError(err instanceof Error ? err.message : 'Unable to connect to the simulation API')
    } finally {
      refreshing.current = false
    }
  }, [selectedProviderId, rangeMinutes])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const delay = data?.simulation.running ? 750 : 2000
    const timer = window.setInterval(() => void refresh(true), delay)
    return () => window.clearInterval(timer)
  }, [data?.simulation.running, refresh])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 3000)
    return () => window.clearTimeout(timer)
  }, [toast])
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'auto' }) }, [page])

  const perform = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true)
    setError(null)
    try {
      await operation()
      setToast(success)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The simulation action failed')
    } finally {
      setBusy(false)
    }
  }

  const manual = (action: ManualAction) => {
    const messages: Record<ManualAction, string> = {
      generate: 'Manual prediction cycle generated', match: 'Manual matching completed', reevaluate: 'Manual re-evaluation completed',
      startContracts: 'Scheduled contracts activated', completeContracts: 'Active contracts settled', fail: 'Provider failure simulated',
    }
    void perform(() => actions[action](), messages[action])
  }

  const createContract = (match: Match) => void perform(() => actions.createContract(match), 'Predictive contract created')
  const openContract = async (id: number) => {
    try { setDrawer(await actions.contractDetail(id) as ContractDetail) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not load contract history') }
  }

  if (!data) return <div className="app-loading"><div className="loading-mark"><CloudIcon /></div><strong>Starting cloud federation</strong><span>{error ?? 'Connecting to the simulation engine...'}</span><div className="loading-track"><i /></div></div>
  const title = page === 'provider' ? data.selected_provider?.provider.name ?? 'Provider detail' : nav.find((item) => item.id === page)?.label ?? 'Live overview'
  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><CloudIcon /></div><div><strong>Concord</strong><span>Federation control</span></div><button type="button" aria-label="Close navigation" className="mobile-close" onClick={() => setMobileNav(false)}><XIcon /></button></div>
      <nav aria-label="Primary navigation">{nav.map(({ id, label, icon: Icon }) => { const active = page === id || (page === 'provider' && id === 'overview'); return <button type="button" aria-current={active ? 'page' : undefined} className={active ? 'active' : ''} key={id} onClick={() => { setPage(id); setMobileNav(false) }}><Icon size={18} /><span>{label}</span>{id === 'contracts' && data.contracts.length > 0 && <em>{data.contracts.length}</em>}</button> })}</nav>
      <div className="sidebar-status"><div><i className={data.simulation.running ? '' : 'paused'} /><span>Engine {data.simulation.running ? 'running' : 'paused'}</span></div><small>4 horizons · simulated forecasts</small></div>
    </aside>
    {mobileNav && <div className="nav-backdrop" onClick={() => setMobileNav(false)} />}
    <main>
      <header className="topbar"><button type="button" aria-label="Open navigation" className="menu-button" onClick={() => setMobileNav(true)}><ListIcon /></button><div><span className="eyebrow">Confidence-aware federation · Phase 3</span><h1>{title}</h1></div><div className="topbar-actions"><div className={`compact-clock ${data.simulation.running ? 'running' : ''}`}><span>Day {data.simulation.day}</span><strong>{data.simulation.clock}</strong></div><button type="button" className="icon-button refresh-button" title="Refresh data" aria-label="Refresh data" onClick={() => void refresh()}><ArrowsClockwiseIcon size={18} /></button><div className="avatar" title="Phase 3">P3</div></div></header>
      <div className="workspace">
        {error && <div className="error-banner"><PulseIcon size={17} /><span>{error}</span><button onClick={() => setError(null)}><XIcon size={16} /></button></div>}
        <SimulationControls
          simulation={data.simulation}
          providers={data.providers}
          busy={busy}
          onToggle={() => void perform(data.simulation.running ? actions.pause : (data.simulation.clock === '08:00:00' ? actions.start : actions.resume), data.simulation.running ? 'Simulation paused' : 'Simulation running')}
          onReset={() => void perform(actions.reset, 'Simulation reset to Day 1')}
          onStep={() => void perform(() => actions.step(5), 'Advanced five simulated minutes')}
          onSpeed={(speed) => void perform(() => actions.speed(speed), `Speed changed to ${speed}×`)}
          onConfigure={(configuration) => void perform(() => actions.configure(configuration), `${configuration.scenario} scenario configured`)}
          onRandomSeed={() => void perform(actions.randomSeed, 'Generated a new stochastic seed')}
          onRestartSameSeed={() => void perform(actions.restartSameSeed, `Restarted seed ${data.simulation.seed}`)}
          onInject={(providerId: number, kind: InjectKind, severity) => void perform(() => actions.injectEvent(providerId, kind, severity), `Injected ${kind} event`)}
          onManual={manual}
        />
        <div className="content-grid">
          <section className="page-content">
            {page === 'overview' && <Dashboard data={data} selectedProviderId={selectedProviderId} onSelectProvider={setSelectedProviderId} onProviderDetails={(id) => { setSelectedProviderId(id); setPage('provider') }} rangeMinutes={rangeMinutes} onRangeChange={setRangeMinutes} />}
            {page === 'provider' && <ProviderDetail data={data.selected_provider} onBack={() => setPage('overview')} />}
            {page === 'predictions' && <Predictions predictions={data.predictions} />}
            {page === 'marketplace' && <Marketplace matches={data.matches} predictions={data.predictions} busy={busy} onCreate={createContract} />}
            {page === 'contracts' && <Contracts contracts={data.contracts} renegotiations={data.renegotiations} onOpen={(id) => void openContract(id)} />}
            {page === 'reputation' && <Reputation providers={data.providers} history={data.reputation} transactions={data.transactions} />}
            {page === 'analytics' && <Analytics data={data} />}
          </section>
          <EventLog events={data.events} providers={data.providers} />
        </div>
      </div>
    </main>
    <ContractDrawer detail={drawer} onClose={() => setDrawer(null)} />
    {toast && <div className="toast">{toast}</div>}
  </div>
}

export default App
