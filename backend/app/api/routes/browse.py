"""GET /laundromats and GET /laundromats/{id}/slots. Public browse endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.services.browse import BrowseService
from app.services.ids import LAUNDROMAT, parse_id
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatListDto, MachineSlotsListDto

router = APIRouter(tags=["browse"])


def get_browse_service(uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]) -> BrowseService:
    return BrowseService(uow_factory)


Service = Annotated[BrowseService, Depends(get_browse_service)]


@router.get(
    "/laundromats",
    operation_id="listLaundromats",
    response_model=LaundromatListDto,
    summary="List laundromats",
)
def list_laundromats(service: Service):
    """Safe and public: no token. Returns every laundromat by name."""
    return to_response(service.list_laundromats())


@router.get(
    "/laundromats/{laundromat_id}/slots",
    operation_id="listSlots",
    response_model=MachineSlotsListDto,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Free and taken slots of one laundromat on one day",
)
def list_slots(
    laundromat_id: str,
    service: Service,
    date: Annotated[str, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")],
):
    """Safe and public. `date` is YYYY-MM-DD in the laundromat's time zone."""
    return to_response(service.list_slots(parse_id(LAUNDROMAT, laundromat_id), date))
