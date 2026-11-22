"""What we remember about one attempt sent with an Idempotency-Key (US-5.2).

Only the record lives here: the shape of what is stored, like OutboxMessage. The logic (when to
store, when to replay, what counts as "the same attempt") is in app/services/idempotency.py,
because the domain knows nothing about requests.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IdempotencyRecord:
    user_id: int  # keys are per caller: two users may pick the same key
    key: str  # the client's Idempotency-Key, 8 to 128 characters
    endpoint: str  # the use case, e.g. "placeHold"
    request_hash: str  # SHA-256 of what was asked (slot and body), to catch a key reused for something else
    error_code: str | None  # None: the attempt succeeded and response_body holds the result
    response_body: dict | None  # the success DTO exactly as it was sent; None for a failure
    created_at: datetime | None = None  # set by the database (its clock decides retention)
