"""Read-model rows for the slots-by-date browse query (not an aggregate)."""
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import MachineType


@dataclass(frozen=True)
class SlotAvailabilityRow:
    machine_id: int
    machine_label: str
    machine_type: MachineType
    slot_id: int
    start_time: datetime
    end_time: datetime
    available: bool  # same rule as MachineSlot.is_available(now)
