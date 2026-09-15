"""Baseline workload patterns and configurable provider personalities.

These functions are the ground truth used by the simulator. Forecast generation
may consult them to create an intentionally imperfect forecast, but marketplace
services only receive persisted Prediction records and never call this module.
"""

from dataclasses import dataclass
from datetime import datetime
from math import pi, sin


@dataclass(frozen=True)
class WorkloadPoint:
    cpu: float
    ram: float


PROVIDER_PERSONALITIES = {
    "Cloud A": {
        "label": "Enterprise office-hours",
        "noise": 0.55,
        "spike_rate": 0.55,
        "drop_rate": 0.18,
        "spike_magnitude": 1.20,
        "base_confidence": 92,
        "preferred_spikes": ["Customer Campaign", "Unexpected Traffic Surge", "Flash Crowd"],
    },
    "Cloud B": {
        "label": "Consumer web",
        "noise": 1.0,
        "spike_rate": 1.35,
        "drop_rate": 0.55,
        "spike_magnitude": 0.78,
        "base_confidence": 84,
        "preferred_spikes": ["API Burst", "Flash Crowd", "Customer Campaign"],
    },
    "Cloud C": {
        "label": "Backend and batch",
        "noise": 0.48,
        "spike_rate": 0.68,
        "drop_rate": 0.30,
        "spike_magnitude": 0.68,
        "base_confidence": 94,
        "preferred_spikes": ["Batch Job", "Video Processing Burst", "API Burst"],
    },
    "Cloud D": {
        "label": "Highly volatile edge traffic",
        "noise": 1.55,
        "spike_rate": 1.85,
        "drop_rate": 0.75,
        "spike_magnitude": 1.0,
        "base_confidence": 72,
        "preferred_spikes": ["Unexpected Traffic Surge", "Flash Crowd", "API Burst"],
    },
}


def personality(provider_name: str) -> dict:
    return PROVIDER_PERSONALITIES.get(provider_name, PROVIDER_PERSONALITIES["Cloud D"])


def _clamp(value: float, low: float = 0.0, high: float = 999.0) -> float:
    return max(low, min(high, value))


def _triangle(hour: float, center: float, half_width: float, height: float) -> float:
    distance = abs(hour - center)
    return height * max(0.0, 1.0 - distance / half_width)


def _ramp(hour: float, start: float, end: float, height: float) -> float:
    return height * _clamp((hour - start) / (end - start), 0.0, 1.0)


def workload_at(provider_name: str, simulation_time: datetime) -> WorkloadPoint:
    hour = simulation_time.hour + simulation_time.minute / 60 + simulation_time.second / 3600
    day_phase = simulation_time.timetuple().tm_yday * 0.31

    if provider_name == "Cloud A":
        # Quiet at 08:00, rising into a sharp 13:00 research-compute peak.
        cpu = 27 + _ramp(hour, 8, 12, 28) + _triangle(hour, 13, 2, 75)
        ram = 66 + _ramp(hour, 8, 12, 34) + _triangle(hour, 13, 2, 140)
        if hour > 15:
            cpu -= _ramp(hour, 15, 20, 32)
            ram -= _ramp(hour, 15, 20, 54)
    elif provider_name == "Cloud B":
        # Busy morning batch jobs, then a steep capacity release after 12:30.
        morning_wave = 4 * sin((hour - 8) * pi / 2 + day_phase)
        if hour < 12.5:
            cpu = 72 + morning_wave
            ram = 168 + 9 * sin((hour - 8) * pi / 2 + 0.4)
        elif hour < 14:
            progress = (hour - 12.5) / 1.5
            cpu = 72 - 38 * progress
            ram = 168 - 67 * progress
        else:
            cpu = 36 + 7 * sin((hour - 14) * pi / 4)
            ram = 105 + 18 * sin((hour - 14) * pi / 4 + 0.4)
    elif provider_name == "Cloud C":
        # Stable service with slow, predictable periodic oscillation.
        cpu = 56 + 7 * sin((hour * pi / 3) + day_phase) + 3 * sin(hour * pi)
        ram = 88 + 13 * sin((hour * pi / 4) + 0.8)
    else:
        # Two repeatable daily peaks around 10:00 and 18:00.
        cpu = 34 + _triangle(hour, 10, 1.5, 61) + _triangle(hour, 18, 2, 52)
        ram = 57 + _triangle(hour, 10, 1.7, 77) + _triangle(hour, 18, 2.2, 63)

    return WorkloadPoint(round(_clamp(cpu), 2), round(_clamp(ram), 2))


def volatility_near(provider_name: str, simulation_time: datetime) -> float:
    """Normalized local change used only to lower confidence near steep ramps."""
    from datetime import timedelta

    before = workload_at(provider_name, simulation_time - timedelta(minutes=15))
    after = workload_at(provider_name, simulation_time + timedelta(minutes=15))
    return round(abs(after.cpu - before.cpu) + abs(after.ram - before.ram) * 0.3, 2)
