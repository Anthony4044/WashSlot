"""The Idempotency-Key header (lecture Ch. 3), checked in the interface layer.

Why a key? Placing a hold is NOT safe and not naturally idempotent: every successful call takes a
slot. If the reply is lost (a timeout), the client can't tell whether its hold went through. The
contract's answer is a key the CLIENT makes up for one attempt (a UUID). A retry of that attempt
sends the SAME key, so the server can recognize it as a repeat instead of a new attempt.

Who does what:
- Here (US-4.1):     the header is required and must be 8 to 128 characters, or 422 idempotency_key_required.
- The service layer  (US-5.2, app/services/idempotency.py): stores the key and the outcome in the same
                     transaction as the hold, and answers a repeat with that stored outcome (the hold is
                     placed at most once). The same key for a different request is 422 idempotency_key_reuse.
"""
from typing import Annotated

from fastapi import Depends, Header

from app.api.errors import ApiError

MIN_KEY_LENGTH = 8  # contract: parameters.IdempotencyKey minLength: 8
MAX_KEY_LENGTH = 128  # contract: parameters.IdempotencyKey maxLength: 128


def require_idempotency_key(key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    """A FastAPI dependency: returns the header's value, or refuses the request with 422 idempotency_key_required.

    We check it ourselves instead of letting FastAPI validate the header, because FastAPI's own
    error would be the generic invalid_request, and the contract promises this specific code.
    """
    if key is None or not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
        raise ApiError("idempotency_key_required")
    return key


# Use it as a route parameter type: `idempotency_key: IdempotencyKey`.
IdempotencyKey = Annotated[str, Depends(require_idempotency_key)]
