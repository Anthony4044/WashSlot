"""A washer or dryer, as the operator manages it (US-7.1)."""
from dataclasses import dataclass

from app.domain.enums import MachineType


@dataclass
class Machine:
    id: int
    laundromat_id: int
    label: str  # e.g. "Washer 4"
    type: MachineType
    reservable: bool  # False: walk-in only, customers can't hold its slots

    def belongs_to(self, laundromat_id: int) -> bool:
        return self.laundromat_id == laundromat_id

    def set_reservable(self, reservable: bool) -> None:
        """Switch between reservable and walk-in only.

        Only NEW holds are affected (MachineSlot.is_available reads this flag): holds and
        reservations made before stay valid, so switching a machine off never breaks a booking.
        """
        self.reservable = reservable
