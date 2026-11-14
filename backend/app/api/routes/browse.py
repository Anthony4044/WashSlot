"""GET /laundromats and (later) GET /laundromats/{id}/slots. Public browse endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.services.browse import BrowseService
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatListDto

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
