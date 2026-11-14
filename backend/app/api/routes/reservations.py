"""GET /me/reservations (US-4.3). Thin interface: parse, call the service, map Outcome to HTTP."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.security import CurrentUser, require_scope
from app.services.reservations import ReservationService
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import ReservationListDto

router = APIRouter(tags=["reservations"])

AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


def get_reservation_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReservationService:
    return ReservationService(uow_factory)


Service = Annotated[ReservationService, Depends(get_reservation_service)]
Reader = Annotated[CurrentUser, Depends(require_scope("reservations:read"))]


@router.get(
    "/me/reservations",
    operation_id="listMyReservations",
    response_model=ReservationListDto,
    responses=AUTH_ERRORS,
    summary="List my reservations",
)
def list_my_reservations(user: Reader, service: Service):
    """Safe. The caller comes from the token; there is no way to ask for someone else's."""
    return to_response(service.list_mine(user.id))
