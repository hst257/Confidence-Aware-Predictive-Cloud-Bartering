import type { Match, SimulationConfiguration, Snapshot } from './types'

// Development requests stay same-origin and are proxied by Vite. Production can
// still point at a separate API with VITE_API_URL.
const API_URL = import.meta.env.VITE_API_URL ?? '/api'

export function experimentExportUrl(format: 'csv' | 'json', runIds: number[] = []) {
  const params = new URLSearchParams({ format })
  if (runIds.length) params.set('run_ids', runIds.join(','))
  return `${API_URL}/experiments/export?${params}`
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? 'The request could not be completed')
  }
  return response.json()
}

export function loadSnapshot(providerId?: number, rangeMinutes = 360): Promise<Snapshot> {
  const params = new URLSearchParams({ range_minutes: String(rangeMinutes) })
  if (providerId) params.set('provider_id', String(providerId))
  return request(`/simulation/snapshot?${params}`)
}

export const actions = {
  reset: () => request('/simulation/reset', { method: 'POST' }),
  start: () => request('/simulation/start', { method: 'POST' }),
  pause: () => request('/simulation/pause', { method: 'POST' }),
  resume: () => request('/simulation/resume', { method: 'POST' }),
  speed: (speed: number) => request('/simulation/speed', { method: 'PATCH', body: JSON.stringify({ speed }) }),
  step: (minutes = 5) => request('/simulation/step', { method: 'POST', body: JSON.stringify({ minutes }) }),
  configure: (configuration: SimulationConfiguration) => request('/simulation/configure', { method: 'PUT', body: JSON.stringify(configuration) }),
  randomSeed: () => request('/simulation/random-seed', { method: 'POST' }),
  restartSameSeed: () => request('/simulation/restart-same-seed', { method: 'POST' }),
  injectEvent: (providerId: number, kind: 'spike' | 'drop' | 'failure', severity: 'info' | 'warning' | 'critical') => request('/simulation/events/inject', { method: 'POST', body: JSON.stringify({ provider_id: providerId, kind, severity }) }),
  generate: () => request('/simulation/generate-predictions', { method: 'POST' }),
  match: () => request<Match[]>('/matching/run', { method: 'POST' }),
  reevaluate: () => request('/simulation/re-evaluate', { method: 'POST' }),
  startContracts: () => request('/simulation/start-contracts', { method: 'POST' }),
  completeContracts: () => request('/simulation/complete-contracts', { method: 'POST' }),
  fail: () => request('/simulation/fail-next', { method: 'POST' }),
  createContract: (match: Match) => request('/contracts', {
    method: 'POST',
    body: JSON.stringify({
      provider_id: match.provider_id,
      consumer_id: match.consumer_id,
      prediction_id: match.prediction_id,
      cpu_amount: match.cpu_amount,
      ram_amount: match.ram_amount,
      start_time: match.window_start,
      end_time: match.window_end,
      match_score: match.match_score,
      selection_reason: match.selection_reason,
    }),
  }),
  contractDetail: (id: number) => request(`/contracts/${id}`),
}
