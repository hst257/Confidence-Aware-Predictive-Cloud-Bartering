export type ResourceState = {
  id: number; run_id: number | null; cpu_usage: number; ram_usage: number; baseline_cpu: number; baseline_ram: number
  usable_cpu: number; usable_ram: number; cpu_capacity_lost: number; ram_capacity_lost: number
  random_noise_cpu: number; random_noise_ram: number; volatility: number; cpu_available: number; ram_available: number
  reserved_future_cpu: number; reserved_future_ram: number; effective_future_cpu: number; effective_future_ram: number
  simulation_time: string | null; observed_at: string; source: string
}

export type Prediction = {
  id: number; run_id: number | null; provider_id: number; provider_name?: string; predicted_cpu_usage: number; predicted_ram_usage: number
  predicted_cpu_spare: number; predicted_ram_spare: number; cpu_deficit: number; ram_deficit: number
  safe_cpu_commitment: number; safe_ram_commitment: number; confidence: number; window_start: string; window_end: string
  generated_at: string; simulation_generated_at: string | null; horizon_minutes: number; cycle_id: string | null
  recent_volatility: number; kind: 'Initial' | 'Revised'; superseded: boolean
}

export type Provider = {
  id: number; name: string; total_cpu: number; total_ram: number; credit_balance: number; sla_reputation: number
  forecast_reliability: number; contribution_score: number; successful_contracts: number; failed_predictions: number
  locked_collateral: number; active_contracts: number; future_commitment_cpu: number; future_commitment_ram: number
  personality: string; current_volatility: number; active_event: string | null; capacity_lost_cpu: number; capacity_lost_ram: number
  current_state: ResourceState | null; latest_prediction: Prediction | null
}

export type Match = {
  provider_id: number; provider_name: string; consumer_id: number; consumer_name: string; prediction_id: number
  demand_prediction_id: number; horizon_minutes: number; cpu_amount: number; ram_amount: number; requested_cpu: number
  requested_ram: number; window_start: string; window_end: string; confidence: number; forecast_reliability: number
  sla_reputation: number; contribution_score: number; safe_cpu_available: number; safe_ram_available: number
  reserved_cpu: number; reserved_ram: number; match_score: number; barter_cost: number; collateral: number
  selection_reason: string
}

export type ContractStatus = 'Proposed' | 'Scheduled' | 'At Risk' | 'Active' | 'Completed' | 'Renegotiated' | 'Failed' | 'Cancelled'

export type Contract = {
  id: number; run_id: number | null; provider_id: number; provider_name: string; consumer_id: number; consumer_name: string
  prediction_id: number | null; parent_contract_id: number | null; cpu_amount: number; ram_amount: number
  start_time: string; end_time: string; barter_cost: number; prediction_confidence: number; status: ContractStatus
  match_score: number; selection_reason: string; actual_cpu_spare: number | null; actual_ram_spare: number | null
  barter_type: 'Predictive' | 'Emergency'; emergency_reason: string | null; reaction_time_minutes: number | null
  collateral: { id: number; amount: number; status: string; locked_at: string; resolved_at: string | null } | null
  created_at: string; updated_at: string; created_simulation_time: string | null
}

export type SystemEvent = {
  id: number; event_type: string; severity: 'info' | 'warning' | 'error'; message: string
  provider_id: number | null; contract_id: number | null; details: Record<string, unknown>
  created_at: string; simulation_time: string | null
}

export type StochasticEvent = {
  id: number; run_id: number; provider_id: number; provider_name: string; event_type: 'workload_spike' | 'workload_drop' | 'capacity_failure'
  name: string; affected_resource: string; start_time: string; end_time: string; magnitude_percent: number
  capacity_loss_percent: number; severity: string; source: string; active: boolean; details: Record<string, unknown>
}

export type Shortage = {
  id: number; provider_id: number; provider_name: string; detected_at: string; cpu_deficit: number; ram_deficit: number
  resolution_type: 'Predictive' | 'Emergency' | 'Unresolved'; outcome: string; contract_ids: number[]
  resolved_at: string | null; reaction_time_minutes: number | null; details: Record<string, unknown>
}

export type ReputationHistory = {
  id: number; provider_id: number; provider_name?: string; contract_id: number | null; metric: string
  old_value: number; new_value: number; forecast_accuracy: number | null; reason: string
  created_at: string; simulation_time: string | null
}

export type CreditTransaction = {
  id: number; provider_id: number; provider_name?: string; contract_id: number | null; amount: number
  transaction_type: string; balance_after: number; description: string; created_at: string; simulation_time: string | null
}

export type Renegotiation = {
  id: number; original_contract_id: number; reason: string; old_cpu: number; old_ram: number
  retained_cpu: number; retained_ram: number; replacement_contract_ids: number[]; created_at: string
  simulation_time: string | null
}

export type ScenarioConfiguration = {
  noise_level: string; noise_multiplier: number; spike_probability: string; spikes_per_hour: number
  drop_probability: string; drops_per_hour: number; failure_probability: string; failures_per_hour: number
  spike_magnitude: string; magnitude_multiplier: number; emergency_threshold: number
}

export type SimulationState = {
  id: number; run_id: number; current_time: string; day: number; clock: string; running: boolean; status: 'Running' | 'Paused'
  speed: number; allowed_speeds: number[]; seed: number; scenario: string; mode: 'Random' | 'Reproducible'; random_mode: boolean
  configuration: ScenarioConfiguration; available_scenarios: string[]; last_sample_at: string | null; last_prediction_at: string | null
}

export type ForecastMetric = {
  provider_id: number; provider_name: string; cpu_mae: number; ram_mae: number; percentage_error: number; forecast_bias: number
  average_confidence: number; predictions_evaluated: number; successful_forecasts: number; failed_forecasts: number
  event_impacted_forecasts: number; success_rate: number
}

export type CalibrationBucket = { bucket: string; prediction_count: number; average_confidence: number; success_rate: number; average_error: number }

export type SimulationRun = {
  id: number; seed: number; scenario: string; random_mode: boolean; status: string; starting_time: string; ending_time: string | null
  simulation_duration_minutes: number; configuration: ScenarioConfiguration; final_statistics: Record<string, unknown>
}

export type AnalyticsSummary = {
  run_id: number; total_cpu_utilization: number; total_ram_utilization: number; utilization_before_barter: number; utilization_after_barter: number
  resource_sharing_cpu: number; resource_sharing_ram: number; cpu_hours_exchanged: number; ram_hours_exchanged: number
  idle_capacity_shared: number; providers_helped: number; shortages_avoided: number; shortages_prevented: number
  emergency_recoveries: number; unresolved_shortages: number; barter_transactions: number; predictive_contracts: number
  emergency_contracts: number; average_reaction_time: number; average_prediction_lead_time: number; renegotiations: number
  failed_contracts: number; credit_circulation: number; average_forecast_accuracy: number
  contract_success_rate: number; renegotiation_rate: number; failure_recovery_rate: number; system_resilience_score: number
  resilience_formula: string; active_events: number; active_failures: number; current_emergencies: number; active_contracts: number
  at_risk_contracts: number; predicted_deficits: number; contract_counts: Record<string, number>; collateral_penalties: number
  providers: Array<{ id: number; name: string; cpu_utilization: number; ram_utilization: number; credits: number; sla_reputation: number; forecast_reliability: number; volatility: number }>
  forecast_metrics: ForecastMetric[]; confidence_calibration: CalibrationBucket[]; runs: SimulationRun[]
}

export type PredictionEvaluation = {
  id: number; prediction_id: number; simulation_time: string; actual_cpu_usage: number; actual_ram_usage: number
  cpu_absolute_error: number; ram_absolute_error: number; percentage_error: number; forecast_bias: number
  event_impacted: boolean; successful: boolean
}

export type SimulationConfiguration = {
  scenario: string; seed: number | null; random_mode: boolean
}

export type ProviderAnalytics = {
  provider: Provider; resource_history: ResourceState[]; predictions: Prediction[]; evaluations: PredictionEvaluation[]
  contracts: Contract[]; transactions: CreditTransaction[]; reputation_history: ReputationHistory[]
  future_reservations: Contract[]; forecast_metrics: ForecastMetric; current_volatility: number
  active_stochastic_events: StochasticEvent[]; stochastic_events: StochasticEvent[]; historical_failures: StochasticEvent[]
  emergency_contracts: number; predictive_contracts: number
}

export type CreditTimeline = {
  provider_id: number; provider_name: string
  points: Array<{ time: string; balance: number; type: string }>
}

export type Snapshot = {
  simulation: SimulationState; providers: Provider[]; predictions: Prediction[]; matches: Match[]; contracts: Contract[]
  events: SystemEvent[]; stochastic_events: StochasticEvent[]; shortages: Shortage[]; analytics: AnalyticsSummary
  transactions: CreditTransaction[]; reputation: ReputationHistory[]; renegotiations: Renegotiation[]
  credit_timelines: CreditTimeline[]; selected_provider: ProviderAnalytics | null
}
