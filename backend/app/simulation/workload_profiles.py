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
    "Cloud E": {
        "label": "Commerce and checkout", "noise": 0.82, "spike_rate": 1.10,
        "drop_rate": 0.35, "spike_magnitude": 0.85, "base_confidence": 87,
        "preferred_spikes": ["Customer Campaign", "Flash Crowd", "API Burst"],
    },
    "Cloud F": {
        "label": "Machine-learning compute", "noise": 0.65, "spike_rate": 0.72,
        "drop_rate": 0.42, "spike_magnitude": 1.05, "base_confidence": 90,
        "preferred_spikes": ["Batch Job", "Video Processing Burst", "API Burst"],
    },
    "Cloud G": {
        "label": "IoT telemetry ingestion", "noise": 1.12, "spike_rate": 1.28,
        "drop_rate": 0.48, "spike_magnitude": 0.72, "base_confidence": 81,
        "preferred_spikes": ["API Burst", "Unexpected Traffic Surge", "Flash Crowd"],
    },
    "Cloud H": {
        "label": "Memory-heavy data analytics", "noise": 0.58, "spike_rate": 0.62,
        "drop_rate": 0.28, "spike_magnitude": 0.80, "base_confidence": 91,
        "preferred_spikes": ["Batch Job", "API Burst", "Customer Campaign"],
    },
    "Cloud I": {
        "label": "Media streaming", "noise": 1.20, "spike_rate": 1.42,
        "drop_rate": 0.60, "spike_magnitude": 0.92, "base_confidence": 80,
        "preferred_spikes": ["Video Processing Burst", "Flash Crowd", "Unexpected Traffic Surge"],
    },
    "Cloud J": {
        "label": "Overnight research batch", "noise": 0.44, "spike_rate": 0.52,
        "drop_rate": 0.38, "spike_magnitude": 0.76, "base_confidence": 93,
        "preferred_spikes": ["Batch Job", "Video Processing Burst", "API Burst"],
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
    elif provider_name == "Cloud E":
        cpu = 48 + _triangle(hour, 12, 3, 48) + _triangle(hour, 19, 2, 38)
        ram = 112 + _triangle(hour, 12, 3.5, 84) + _triangle(hour, 19, 2.5, 56)
    elif provider_name == "Cloud F":
        cpu = 62 + _triangle(hour, 14, 4, 105) + 7 * sin(hour * pi / 3)
        ram = 132 + _triangle(hour, 14, 4, 116) + 11 * sin(hour * pi / 4)
    elif provider_name == "Cloud G":
        cpu = 32 + 9 * sin(hour * pi / 2 + day_phase) + _triangle(hour, 9, 1.5, 27)
        ram = 66 + 14 * sin(hour * pi / 3) + _triangle(hour, 9, 2, 32)
    elif provider_name == "Cloud H":
        cpu = 54 + 10 * sin(hour * pi / 4) + _triangle(hour, 15, 3, 42)
        ram = 164 + 24 * sin(hour * pi / 5) + _triangle(hour, 15, 3, 172)
    elif provider_name == "Cloud I":
        cpu = 38 + _triangle(hour, 13, 2, 26) + _triangle(hour, 21, 3, 72)
        ram = 82 + _triangle(hour, 13, 2, 42) + _triangle(hour, 21, 3.5, 118)
    elif provider_name == "Cloud J":
        cpu = 70 + _triangle(hour, 2, 3, 112) + _triangle(hour, 23, 2, 86)
        ram = 118 + _triangle(hour, 2, 3, 126) + _triangle(hour, 23, 2, 98)
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
