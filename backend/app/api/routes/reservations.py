"""GET /me/reservations, GET /reservations/{id} (US-4.3), DELETE /reservations/{id} (US-5.3).

Thin interface: parse, call the service, map Outcome to HTTP. Ownership is in the service.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.security import CurrentUser, require_scope
from app.domain.user import OPERATOR_MANAGE
from app.services.ids import RESERVATION, parse_id
from app.services.reservations import ReservationService
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import ReservationDto, ReservationListDto

router = APIRouter(tags=["reservations"])

AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def get_reservation_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReservationService:
    return ReservationService(uow_factory)


Service = Annotated[ReservationService, Depends(get_reservation_service)]
Reader = Annotated[CurrentUser, Depends(require_scope("reservations:read"))]
Writer = Annotated[CurrentUser, Depends(require_scope("reservations:write"))]


@router.get(
    "/me/reservations",
    operation_id="listMyReservations",
    response_model=ReservationListDto,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    summary="List my reservations",
)
def list_my_reservations(user: Reader, service: Service):
    """Safe. The caller comes from the token; there is no way to ask for someone else's."""
    return to_response(service.list_mine(user.id))


@router.get(
    "/reservations/{reservation_id}",
    operation_id="getReservation",
    response_model=ReservationDto,
    responses=AUTH_ERRORS,
    summary="Fetch one of my reservations",
)
def get_reservation(reservation_id: str, user: Reader, service: Service):
    """Safe. Someone else's reservation is 404 not_found."""
    return to_response(service.get(user.id, parse_id(RESERVATION, reservation_id)))


@router.delete(
    "/reservations/{reservation_id}",
    operation_id="cancelReservation",
    status_code=204,
    responses={**AUTH_ERRORS, 409: {"model": ErrorResponse}},
    summary="Cancel one of my reservations",
)
def cancel_reservation(reservation_id: str, user: Writer, service: Service):
    """Only before the slot starts. Already cancelled → 204 again. Someone else's → 404."""
    return to_response(service.cancel(user.id, parse_id(RESERVATION, reservation_id)), 204)


@router.post(
    "/reservations/{reservation_id}/check-in",
    operation_id="checkIn",
    response_model=ReservationDto,
    responses={**AUTH_ERRORS, 409: {"model": ErrorResponse}},
    summary="Check in for a reservation",
)
def check_in(reservation_id: str, user: Writer, service: Service):
    return to_response(service.check_in(
        user.id, parse_id(RESERVATION, reservation_id), is_operator=user.has_scope(OPERATOR_MANAGE),
    ))
