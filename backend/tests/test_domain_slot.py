"""Domain tests: plain objects, no database, microseconds."""
from datetime import UTC, datetime, timedelta

from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation

NOW = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)


def slot_with(*reservations: Reservation) -> MachineSlot:
    return MachineSlot(id=1, machine_id=1, start_time=NOW + timedelta(hours=1), end_time=NOW + timedelta(hours=2),
                       reservations=list(reservations))


def res(status: ReservationStatus, expires_in_min: int | None = 10) -> Reservation:
    expires = NOW + timedelta(minutes=expires_in_min) if expires_in_min is not None else None
    return Reservation(id=None, slot_id=1, user_id=1, status=status, confirmation_email="a@b.c", expires_at=expires)


def test_empty_slot_is_available():
    assert slot_with().is_available(NOW)


def test_live_hold_and_confirmed_reservation_take_the_slot():
    assert not slot_with(res(ReservationStatus.HELD)).is_available(NOW)
    assert not slot_with(res(ReservationStatus.CONFIRMED, None)).is_available(NOW)


def test_expired_cancelled_and_no_show_do_not_take_the_slot():
    stale_hold = res(ReservationStatus.HELD, expires_in_min=-1)
    others = [res(s) for s in (ReservationStatus.EXPIRED, ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW)]
    assert slot_with(stale_hold, *others).is_available(NOW)


def test_a_hold_expires_exactly_at_expires_at():
    assert slot_with(res(ReservationStatus.HELD, expires_in_min=0)).is_available(NOW)


def test_expire_stale_holds_marks_only_stale_holds():
    stale, live = res(ReservationStatus.HELD, -1), res(ReservationStatus.HELD, 5)
    slot = slot_with(stale, live)
    assert slot.expire_stale_holds(NOW) == [stale]
    assert stale.status == ReservationStatus.EXPIRED
    assert live.status == ReservationStatus.HELD
