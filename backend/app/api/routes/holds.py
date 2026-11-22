"""POST /slots/{slotId}/holds, GET /holds/{holdId} and POST /holds/{holdId}/confirm.

The INTERFACE layer (lecture Ch. 5). Thin: parse, call the service, map the Outcome to HTTP.
No rule lives here: "one active reservation per slot" is in the domain, the lock is in the service.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.idempotency import IdempotencyKey
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.schemas.holds import HoldRequest
from app.api.security import CurrentUser, require_scope
from app.core.config import get_settings
from app.services.holds import HoldService
from app.services.ids import HOLD, SLOT, parse_id
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import HoldDto, ReservationDto

router = APIRouter(tags=["holds"])

AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def get_hold_service(uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]) -> HoldService:
    return HoldService(uow_factory, hold_minutes=get_settings().hold_minutes)  # HOLD_MINUTES, 10 by default


Service = Annotated[HoldService, Depends(get_hold_service)]
# Authentication + authorization as dependencies (Ch. 8): no token -> 401, token without the scope -> 403.
Reader = Annotated[CurrentUser, Depends(require_scope("reservations:read"))]
Writer = Annotated[CurrentUser, Depends(require_scope("reservations:write"))]


@router.post(
    "/slots/{slot_id}/holds",
    operation_id="placeHold",  # the same operationId as the contract
    status_code=201,
    response_model=HoldDto,
    responses={**AUTH_ERRORS, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Hold a slot for 10 minutes",
)
def place_hold(slot_id: str, body: HoldRequest, user: Writer, idempotency_key: IdempotencyKey, service: Service):
    """Contract responses: 201 Hold · 401 · 403 · 404 not_found · 409 slot_unavailable · 422.

    FastAPI checks things in the order of the parameters: first the token (`user`: 401/403), then the
    Idempotency-Key header (422 idempotency_key_required), then the body (422 invalid_request).
    Only a request that passes all three reaches the service.

    Ch. 3: NOT safe and not naturally idempotent, which is why the key is required. The service
    stores each attempt's outcome under the key (US-5.2): a repeat gets the same status and body
    back, with Idempotency-Replayed: true, and never a second hold.
    """
    # "slot_5" -> 5. A malformed or wrong-prefix id ("abc", "lm_5") raises NotFound -> 404 not_found.
    # (That 404 happens before the service, so it is not stored: repeating it gives the same 404 anyway.)
    # The customer is `user.id`, from the verified token: never from the body.
    outcome = service.place_hold(user.id, parse_id(SLOT, slot_id), body.confirmation_email, idempotency_key)
    return to_response(outcome, 201)  # Outcome -> 201 + Hold, or {"error": code}; a replay adds the header


@router.get("/holds/{hold_id}", response_model=HoldDto, responses=AUTH_ERRORS, summary="Fetch one of my holds")
def get_hold(hold_id: str, user: Reader, service: Service):
    """Safe. Someone else's hold is 404 not_found."""
    return to_response(service.get_hold(user.id, parse_id(HOLD, hold_id)))


@router.post(
    "/holds/{hold_id}/confirm",
    response_model=ReservationDto,
    responses={**AUTH_ERRORS, 409: {"model": ErrorResponse}},
    summary="Confirm my hold before it expires",
)
def confirm_hold(hold_id: str, user: Writer, service: Service):
    """Naturally idempotent: confirming again returns the same reservation. 409 hold_expired / already_cancelled."""
    return to_response(service.confirm(user.id, parse_id(HOLD, hold_id)))
