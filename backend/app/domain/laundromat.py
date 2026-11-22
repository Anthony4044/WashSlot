"""A laundromat as the browse read model sees it (no aggregate behaviour yet)."""
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
    operator_id: int | None = None


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
