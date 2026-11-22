"""Operator endpoints (US-7.1): my laundromats, their machines, the reservable switch, create slots.

Thin interface: the scope check is a dependency (no token -> 401, a customer's token -> 403), then
parse and call the service. WHICH laundromat the operator may touch is decided in the service.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_uow_factory
from app.api.responses import to_response
from app.api.schemas.errors import ErrorResponse
from app.api.schemas.operator import CreateSlotsRequest, MachineUpdateRequest
from app.api.security import CurrentUser, require_scope
from app.services.ids import LAUNDROMAT, MACHINE, parse_id
from app.services.operator import OperatorService
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatListDto, MachineDto, MachineListDto, SlotsCreatedDto

router = APIRouter(prefix="/operator", tags=["operator"])

AUTH_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}
OWNED_ERRORS = {**AUTH_ERRORS, 404: {"model": ErrorResponse}}


def get_operator_service(uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]) -> OperatorService:
    return OperatorService(uow_factory)


Service = Annotated[OperatorService, Depends(get_operator_service)]
Operator = Annotated[CurrentUser, Depends(require_scope("operator:manage"))]


@router.get("/laundromats", operation_id="listOperatorLaundromats", response_model=LaundromatListDto,
            responses=AUTH_ERRORS, summary="List the laundromats I operate")
def list_my_laundromats(user: Operator, service: Service):
    """Safe. Only the caller's own laundromats."""
    return to_response(service.list_laundromats(user.id))


@router.get("/laundromats/{laundromat_id}/machines", operation_id="listOperatorMachines",
            response_model=MachineListDto, responses=OWNED_ERRORS,
            summary="List the machines of a laundromat I operate")
def list_machines(laundromat_id: str, user: Operator, service: Service):
    """Safe. Another operator's laundromat is 404 not_found."""
    return to_response(service.list_machines(user.id, parse_id(LAUNDROMAT, laundromat_id)))


@router.patch("/laundromats/{laundromat_id}/machines/{machine_id}", operation_id="updateMachine",
              response_model=MachineDto, responses={**OWNED_ERRORS, 422: {"model": ErrorResponse}},
              summary="Switch a machine between reservable and walk-in only")
def update_machine(laundromat_id: str, machine_id: str, user: Operator, body: MachineUpdateRequest,
                   service: Service):
    """Idempotent. 404 for another operator's laundromat or a machine that isn't in this one."""
    outcome = service.set_reservable(user.id, parse_id(LAUNDROMAT, laundromat_id), parse_id(MACHINE, machine_id),
                                     body.reservable)
    return to_response(outcome)


@router.post("/laundromats/{laundromat_id}/slots", operation_id="createSlots", response_model=SlotsCreatedDto,
             responses={**OWNED_ERRORS, 422: {"model": ErrorResponse}}, summary="Create slots for a date range")
def create_slots(laundromat_id: str, user: Operator, body: CreateSlotsRequest, service: Service):
    """Idempotent: existing slots are skipped. 422 for a schedule that breaks the rules (see the contract)."""
    machine_ids = None if body.machine_ids is None else [parse_id(MACHINE, i) for i in body.machine_ids]
    outcome = service.create_slots(
        user.id, parse_id(LAUNDROMAT, laundromat_id),
        from_date=body.from_date, to_date=body.to_date, open_time=body.open_time, close_time=body.close_time,
        slot_minutes=body.slot_minutes, machine_ids=machine_ids,
    )
    return to_response(outcome)
