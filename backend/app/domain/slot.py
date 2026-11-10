"""The MachineSlot aggregate.

A MachineSlot (e.g. Washer 4, 18:00-19:00) is the aggregate ROOT; its Reservations live inside it.
The outside world changes a reservation only through the slot, so the invariant
"at most one active reservation per slot" has exactly one guarded door. It is also the unit we
lock (SELECT ... FOR UPDATE on the slot row) and the unit the repository loads and saves.

Stories add their use-case methods here (place_hold: US-4.1, confirm: US-4.2, cancel: US-5.3,
check_in: US-7.2). Times are always timezone-aware; `now` is passed in (the database clock).
"""
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import MachineType, ReservationStatus
from app.domain.errors import AlreadyCancelled, HoldExpired, NotFound

ACTIVE_STATUSES = (ReservationStatus.HELD, ReservationStatus.CONFIRMED)


@dataclass
class Reservation:
    """Entity inside the slot aggregate: a hold (HELD) and, once confirmed, the reservation."""

    id: int | None  # None until the data layer saves it
    slot_id: int
    user_id: int
    status: ReservationStatus
    confirmation_email: str
    expires_at: datetime | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    checked_in_at: datetime | None = None
    created_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """Does this reservation still take the slot? A HELD past its expiry does not."""
        if self.status == ReservationStatus.CONFIRMED:
            return True
        return self.status == ReservationStatus.HELD and self.expires_at is not None and self.expires_at > now


@dataclass
class MachineSlot:
    """Aggregate root: one reservable period on one machine."""

    id: int
    machine_id: int
    start_time: datetime
    end_time: datetime
    reservations: list[Reservation] = field(default_factory=list)

    def reservation(self, reservation_id: int) -> Reservation | None:
        return next((r for r in self.reservations if r.id == reservation_id), None)

    def active_reservation(self, now: datetime) -> Reservation | None:
        return next((r for r in self.reservations if r.is_active(now)), None)

    def is_available(self, now: datetime) -> bool:
        """THE availability rule, stated once. Read models must agree with it (pinned by a test)."""
        return self.active_reservation(now) is None

    def expire_stale_holds(self, now: datetime) -> list[Reservation]:
        """Lazy expiry: mark holds past their expiry as EXPIRED.

        Must run before placing a new hold in the same transaction: the database's partial unique
        index still counts a stale HELD row as active until its status changes.
        """
        expired = []
        for r in self.reservations:
            if r.status == ReservationStatus.HELD and r.expires_at is not None and r.expires_at <= now:
                r.status = ReservationStatus.EXPIRED
                expired.append(r)
        return expired

    def confirm(self, reservation_id: int, now: datetime) -> Reservation:
        """Turn a live hold into a CONFIRMED reservation (US-4.2). `now` is the database clock.

        Naturally idempotent: a reservation that was already confirmed is returned as it is.
        The caller checks ownership first; this rule only knows about time and state.
        """
        r = self.reservation(reservation_id)
        if r is None:
            raise NotFound()
        if r.status in (ReservationStatus.CONFIRMED, ReservationStatus.NO_SHOW):
            return r  # confirmed earlier: same answer again
        if r.status == ReservationStatus.CANCELLED:
            raise AlreadyCancelled()
        if not r.is_active(now):  # EXPIRED, or HELD at or past its expiry
            raise HoldExpired()
        r.status = ReservationStatus.CONFIRMED
        r.confirmed_at = now
        return r


@dataclass(frozen=True)
class SlotDetails:
    """Where and when a slot is, for showing it to people. Read-only: no rule depends on it."""

    slot_id: int
    laundromat_id: int
    laundromat_name: str
    machine_id: int
    machine_label: str
    machine_type: MachineType
    start_time: datetime
    end_time: datetime
