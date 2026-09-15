"""Phase 3 stochastic scenario configuration.

Probabilities are expressed per simulated provider-hour, so changing wall-clock
speed never changes event density within simulated time.
"""

SCENARIO_PRESETS: dict[str, dict] = {
    "Stable": {
        "noise_level": "Low", "noise_multiplier": 0.45,
        "spike_probability": "Low", "spikes_per_hour": 0.025,
        "drop_probability": "Low", "drops_per_hour": 0.010,
        "failure_probability": "Very Low", "failures_per_hour": 0.002,
        "spike_magnitude": "Low", "magnitude_multiplier": 0.65,
        "emergency_threshold": 3.0,
    },
    "Normal": {
        "noise_level": "Medium", "noise_multiplier": 1.0,
        "spike_probability": "Medium", "spikes_per_hour": 0.075,
        "drop_probability": "Medium", "drops_per_hour": 0.030,
        "failure_probability": "Low", "failures_per_hour": 0.008,
        "spike_magnitude": "Medium", "magnitude_multiplier": 1.0,
        "emergency_threshold": 2.0,
    },
    "Volatile": {
        "noise_level": "High", "noise_multiplier": 1.65,
        "spike_probability": "High", "spikes_per_hour": 0.16,
        "drop_probability": "High", "drops_per_hour": 0.070,
        "failure_probability": "Low", "failures_per_hour": 0.012,
        "spike_magnitude": "High", "magnitude_multiplier": 1.35,
        "emergency_threshold": 1.5,
    },
    "Failure Test": {
        "noise_level": "Medium", "noise_multiplier": 1.0,
        "spike_probability": "Medium", "spikes_per_hour": 0.07,
        "drop_probability": "Medium", "drops_per_hour": 0.035,
        "failure_probability": "Medium", "failures_per_hour": 0.075,
        "spike_magnitude": "Medium", "magnitude_multiplier": 1.0,
        "emergency_threshold": 1.0,
    },
    "Stress Test": {
        "noise_level": "High", "noise_multiplier": 2.15,
        "spike_probability": "High", "spikes_per_hour": 0.28,
        "drop_probability": "High", "drops_per_hour": 0.10,
        "failure_probability": "Medium", "failures_per_hour": 0.055,
        "spike_magnitude": "High", "magnitude_multiplier": 1.7,
        "emergency_threshold": 0.5,
    },
}

DEFAULT_SCENARIO = "Normal"
DEFAULT_SEED = 4281


def scenario_configuration(name: str) -> dict:
    if name not in SCENARIO_PRESETS:
        raise ValueError(f"Unknown scenario: {name}")
    return dict(SCENARIO_PRESETS[name])

