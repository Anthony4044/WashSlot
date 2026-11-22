"""Request bodies of the operator endpoints (US-7.1). Strict like every request body: unknown fields are 422."""
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StrictBool, field_validator

from app.api.schemas.base import RequestModel

# contract: LocalTime. "08:00" in the laundromat's time zone; "24:00" is midnight at the end of the day.
LocalTime = Annotated[str, Field(pattern=r"^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$")]


class MachineUpdateRequest(RequestModel):
    """contract: MachineUpdate = {reservable}."""

    reservable: StrictBool  # strict: "yes" or 1 is 422, not quietly turned into True


class CreateSlotsRequest(RequestModel):
    """contract: CreateSlotsRequest. The date and time RULES (range, order, fit) are the domain's
    (app/domain/schedule.py); this model only checks the shapes."""

    machine_ids: list[str] | None = Field(default=None, min_length=1)  # None: every reservable machine
    from_date: date
    to_date: date
    open_time: LocalTime
    close_time: LocalTime
    slot_minutes: Literal[30, 60, 90]

    @field_validator("machine_ids")
    @classmethod
    def _unique(cls, ids: list[str] | None) -> list[str] | None:
        if ids is not None and len(set(ids)) != len(ids):
            raise ValueError("machineIds must not repeat")  # contract: uniqueItems
        return ids
