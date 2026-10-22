"""Half-open reservation windows shared by planning, risk, and live delivery."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BarterContract, ContractStatus

OPEN_STATUSES = [ContractStatus.PROPOSED, ContractStatus.SCHEDULED, ContractStatus.AT_RISK, ContractStatus.ACTIVE]


def overlaps(db: Session, run_id: int, provider_id: int, start: datetime, end: datetime, *, incoming: bool = False) -> list[BarterContract]:
    party = BarterContract.consumer_id if incoming else BarterContract.provider_id
    return list(db.scalars(select(BarterContract).where(
        BarterContract.run_id == run_id, party == provider_id,
        BarterContract.status.in_(OPEN_STATUSES),
        BarterContract.start_time < end, BarterContract.end_time > start,
    )).all())


def segments(contracts: list[BarterContract], start: datetime, end: datetime):
    boundaries = {start, end}
    for item in contracts:
        if item.start_time < end and item.end_time > start:
            boundaries.update((max(start, item.start_time), min(end, item.end_time)))
    points = sorted(boundaries)
    for left, right in zip(points, points[1:]):
        active = [item for item in contracts if item.start_time <= left and item.end_time >= right]
        yield left, right, sum(item.cpu_amount for item in active), sum(item.ram_amount for item in active)


def peak(contracts: list[BarterContract], start: datetime, end: datetime) -> tuple[float, float]:
    windows = list(segments(contracts, start, end))
    return max((item[2] for item in windows), default=0), max((item[3] for item in windows), default=0)
