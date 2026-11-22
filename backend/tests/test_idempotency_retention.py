"""US-5.2 (T.5.2.5): Idempotency-Key records are kept at least 24 hours, then the worker forgets them.

What we prove:
- the sweep deletes only records OLDER than the retention, never a younger one
- on the database it uses the database clock (the clock that stamped created_at)
- the worker runs it, and a retention under the contract's 24 hours is refused at startup
"""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

import worker
from app.core.config import Settings
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import IdempotencyRecordRow
from app.domain.idempotency import IdempotencyRecord
from app.services.idempotency import delete_old_records
from tests.factories import make_user

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def record(key: str, user_id: int = 1) -> IdempotencyRecord:
    return IdempotencyRecord(user_id=user_id, key=key, endpoint="placeHold", request_hash="h",
                             error_code="not_found", response_body=None)


# --- the rule, in memory --------------------------------------------------------------------------

def test_only_records_older_than_the_retention_are_deleted():
    clock = Clock()
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))
    for hours_ago in (25, 24, 23):  # stored 25, 24 and 23 hours before the sweep
        clock.now = NOW - timedelta(hours=hours_ago)
        uow.idempotency.add(record(f"made-{hours_ago}h-ago"))
    clock.now = NOW

    deleted = delete_old_records(uow, retention_hours=24)

    assert deleted == 1
    assert uow.idempotency.get(1, "made-25h-ago") is None  # older than 24 hours: forgotten
    assert uow.idempotency.get(1, "made-24h-ago") is not None  # exactly 24 hours: still promised
    assert uow.idempotency.get(1, "made-23h-ago") is not None


# --- on the database: the database clock decides ---------------------------------------------------

def insert_record(db_session, user_id: int, key: str, age: str) -> None:
    """A record whose created_at is `age` before the DATABASE's now(), e.g. age='25 hours'."""
    db_session.add(IdempotencyRecordRow(user_id=user_id, key=key, endpoint="placeHold", request_hash="h",
                                        error_code="not_found",
                                        created_at=func.now() - text(f"interval '{age}'")))
    db_session.flush()


def keys_left(db_session) -> set[str]:
    db_session.expire_all()
    return set(db_session.scalars(select(IdempotencyRecordRow.key)))


def test_the_sweep_on_the_database_keeps_every_key_younger_than_24_hours(db_session, uow_factory):
    user = make_user(db_session)
    insert_record(db_session, user.id, "two-days-old", "48 hours")
    insert_record(db_session, user.id, "just-over", "24 hours 1 minute")
    insert_record(db_session, user.id, "just-under", "23 hours 59 minutes")
    insert_record(db_session, user.id, "brand-new", "0 seconds")
    db_session.commit()

    deleted = delete_old_records(uow_factory, retention_hours=24)

    assert deleted == 2
    assert keys_left(db_session) == {"just-under", "brand-new"}


def test_the_worker_job_forgets_old_keys(db_session, uow_factory):
    user = make_user(db_session)
    insert_record(db_session, user.id, "old", "25 hours")
    insert_record(db_session, user.id, "young", "1 hour")
    db_session.commit()

    worker.forget_old_idempotency_keys(uow_factory)  # uses IDEMPOTENCY_RETENTION_HOURS (24 by default)

    assert keys_left(db_session) == {"young"}


# --- wiring ----------------------------------------------------------------------------------------

def test_the_worker_runs_the_sweep():
    assert worker.forget_old_idempotency_keys in [job for _, job, _ in worker.JOBS]


def test_a_retention_under_24_hours_is_refused():
    """The contract promises 24 hours: a config that would break the promise fails at startup."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, idempotency_retention_hours=23)
    assert Settings(_env_file=None).idempotency_retention_hours == 24
