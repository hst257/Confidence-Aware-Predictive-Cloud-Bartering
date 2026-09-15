"""Serialize simulation mutations across request threads and app workers.

The simulator has one shared clock and one shared set of provider balances.  A
background tick and an API action therefore have to behave like one-at-a-time
transactions.  The process lock covers SQLite and threads; PostgreSQL's
transaction-scoped advisory lock also covers reloads and multiple workers.
"""

from contextlib import contextmanager
from threading import RLock
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session


_process_lock = RLock()
_POSTGRES_LOCK_ID = 424_204_001


@contextmanager
def simulation_mutation(db: Session) -> Iterator[None]:
    with _process_lock:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": _POSTGRES_LOCK_ID},
            )
        try:
            yield
        except Exception:
            db.rollback()
            raise
