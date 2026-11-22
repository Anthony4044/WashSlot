"""Idempotency-Key handling (US-5.2), in the SERVICE layer (CODING_GUIDE section 7).

Why here? Not in the domain, which knows nothing about requests. Not in the route, because another
protocol (a CLI, a message queue) would skip it. Every caller of the use case gets it.

The problem: placing a hold is NOT idempotent (each success takes a slot). If the response is lost,
the client can't tell whether its hold went through, so it retries with the SAME key. This module
turns that retry into a replay of the first answer instead of a second attempt:

    BEGIN
      SELECT the record for (user, key)          -- found? replay it (or 422 if it was for something else)
      ... the use case: lock the slot, decide, write ...
      INSERT the record ON CONFLICT DO NOTHING   -- 0 rows? a twin got there first
    COMMIT                                       -- the hold and its record land together, or neither does

The twin case is two copies of one request racing (a double click, a retry that overtakes a slow
original). Both miss the SELECT, but the primary key (user_id, key) lets only one INSERT through.
The loser rolls back ITS work (so no second hold), then replays the winner's stored outcome.

"The same attempt" means the same user, the same use case and the same request (slot and body).
Whatever the first attempt got (success, not_found, slot_unavailable) is what every repeat gets.
"""
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from app.domain.idempotency import IdempotencyRecord
from app.services.dto import Dto
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWork, UnitOfWorkFactory


@dataclass(frozen=True)
class Attempt:
    """One request sent with an Idempotency-Key."""

    user_id: int
    key: str
    endpoint: str  # the use case's name, e.g. "placeHold" (the contract's operationId)
    request_hash: str

    @classmethod
    def of(cls, user_id: int, key: str, endpoint: str, **request) -> "Attempt":
        """Attempt.of(7, key, "placeHold", slot_id=5, confirmation_email="kim@example.com")"""
        return cls(user_id=user_id, key=key, endpoint=endpoint, request_hash=request_hash(**request))


def request_hash(**request) -> str:
    """SHA-256 of the request's fields, in a fixed order, so the same request always gives the same hash."""
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _TwinWon(Exception):
    """Raised inside the unit of work to roll it back: a twin request already stored this key."""


def run_once(
    uow_factory: UnitOfWorkFactory,
    attempt: Attempt,
    dto_type: type[Dto],
    use_case: Callable[[UnitOfWork], Outcome],
) -> Outcome:
    """Run `use_case` at most once per attempt, and answer every repeat with the stored outcome.

    `use_case(uow)` does its work inside OUR unit of work and RETURNS its Outcome (a refusal like
    slot_unavailable must be returned, not raised, so that it is stored too). It must write nothing
    when it fails: the refusal's record is still committed.
    """
    try:
        with uow_factory() as uow:  # BEGIN
            earlier = uow.idempotency.get(attempt.user_id, attempt.key)
            if earlier is not None:
                return _replay(earlier, attempt, dto_type)  # a repeat: no lock taken, nothing written
            outcome = use_case(uow)
            if not uow.idempotency.add(_record(attempt, outcome)):
                raise _TwinWon()  # leaves the block with an exception: ROLLBACK, our hold is gone
            return outcome  # COMMIT happens as the block exits, before the caller sees the outcome
    except _TwinWon:
        with uow_factory() as uow:  # a new transaction, which sees the twin's committed record
            earlier = uow.idempotency.get(attempt.user_id, attempt.key)
        if earlier is None:  # can't happen: ON CONFLICT only skips a row that was committed
            raise RuntimeError(f"idempotency record {attempt.key!r} vanished after a conflict") from None
        return _replay(earlier, attempt, dto_type)


def _record(attempt: Attempt, outcome: Outcome) -> IdempotencyRecord:
    """What we store: the error code, or the success DTO exactly as it goes on the wire."""
    return IdempotencyRecord(
        user_id=attempt.user_id,
        key=attempt.key,
        endpoint=attempt.endpoint,
        request_hash=attempt.request_hash,
        error_code=None if outcome.ok else outcome.code,
        response_body=outcome.value.model_dump(mode="json") if outcome.ok else None,
    )


def _replay(earlier: IdempotencyRecord, attempt: Attempt, dto_type: type[Dto]) -> Outcome:
    """The stored outcome, marked as replayed. The same key for a different request is a client bug."""
    if earlier.endpoint != attempt.endpoint or earlier.request_hash != attempt.request_hash:
        return Outcome.failure("idempotency_key_reuse")
    if earlier.error_code is not None:
        return Outcome(ok=False, code=earlier.error_code, replayed=True)
    return Outcome(ok=True, value=dto_type.model_validate(earlier.response_body), replayed=True)


def delete_old_records(uow_factory: UnitOfWorkFactory, retention_hours: int) -> int:
    """Worker job (T.5.2.5): forget keys older than `retention_hours`. Returns how many were deleted.

    The contract promises keys are kept at least 24 hours, so a younger key is never deleted: the
    cut-off uses the database clock (the same clock that stamped created_at), not the worker's.
    """
    with uow_factory() as uow:
        return uow.idempotency.delete_older_than(retention_hours)
