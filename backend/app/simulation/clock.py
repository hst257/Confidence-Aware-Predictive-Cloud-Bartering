from datetime import datetime, timedelta

from ..config import get_settings


def simulation_epoch() -> datetime:
    return datetime.fromisoformat(get_settings().simulation_start_iso)


def advance_time(current: datetime, real_seconds: float, speed: int) -> datetime:
    return current + timedelta(seconds=max(0.0, real_seconds) * speed)


def display_time(current: datetime) -> tuple[int, str]:
    elapsed = current - simulation_epoch()
    day = max(1, elapsed.days + 1)
    return day, current.strftime("%H:%M:%S")

