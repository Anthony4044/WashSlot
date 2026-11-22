"""HTTP routes for the operator's assigned laundromats."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.security import CurrentUser, require_scope
from app.domain.user import OPERATOR_MANAGE
from app.services.ids import LAUNDROMAT, parse_id
from app.services.operator import OperatorService
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatListDto, TodayBookingsDto

router = APIRouter(prefix="/operator/laundromats", tags=["operator"])
AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


def get_operator_service(uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]) -> OperatorService:
    return OperatorService(uow_factory)


Operator = Annotated[CurrentUser, Depends(require_scope(OPERATOR_MANAGE))]
Service = Annotated[OperatorService, Depends(get_operator_service)]


@router.get("", operation_id="listOperatorLaundromats", response_model=LaundromatListDto, responses=AUTH_ERRORS)
def list_operator_laundromats(user: Operator, service: Service):
    return to_response(service.list_laundromats(user.id))


@router.get(
    "/{laundromat_id}/today",
    operation_id="listTodaysBookings",
    response_model=TodayBookingsDto,
    responses={**AUTH_ERRORS, 404: {"model": ErrorResponse}},
)
def list_todays_bookings(laundromat_id: str, user: Operator, service: Service):
    return to_response(service.today(user.id, parse_id(LAUNDROMAT, laundromat_id)))
