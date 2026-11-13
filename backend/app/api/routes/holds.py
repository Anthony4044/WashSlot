"""GET /holds/{holdId} and POST /holds/{holdId}/confirm. Thin: parse, call the service, map the Outcome.

US-4.1 adds POST /slots/{slotId}/holds here.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.security import CurrentUser, require_scope
from app.services.holds import HoldService
from app.services.ids import HOLD, parse_id
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import HoldDto, ReservationDto

router = APIRouter(tags=["holds"])

AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def get_hold_service(uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]) -> HoldService:
    return HoldService(uow_factory)


Service = Annotated[HoldService, Depends(get_hold_service)]
Reader = Annotated[CurrentUser, Depends(require_scope("reservations:read"))]
Writer = Annotated[CurrentUser, Depends(require_scope("reservations:write"))]


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
