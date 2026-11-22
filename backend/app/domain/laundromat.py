"""A laundromat: what browsing shows, plus who operates it (US-7.1)."""
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ReservationStatus

BOOKING_STATUSES = (ReservationStatus.CONFIRMED, ReservationStatus.NO_SHOW)


@dataclass(frozen=True)
class Laundromat:
    id: int
    name: str
    address: str
    timezone: str
    operator_id: int | None = None  # the user who runs it; None until an operator is linked

    def is_run_by(self, user_id: int) -> bool:
        """THE ownership rule for operator tools: only the laundromat's own operator may change it."""
        return self.operator_id is not None and self.operator_id == user_id


@dataclass(frozen=True)
class TodayBooking:
    """One row of the operator's read model."""

    reservation_id: int
    machine_label: str
    start_time: datetime
    end_time: datetime
    customer_email: str
    status: ReservationStatus
    checked_in_at: datetime | None
