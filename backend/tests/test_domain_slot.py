"""Domain tests: plain objects, no database, microseconds."""
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import ReservationStatus
from app.domain.errors import AlreadyCancelled, HoldExpired, NotFound
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


# --- confirm (US-4.2) -----------------------------------------------------------------------

def held(expires_in_min: int = 10, status: ReservationStatus = ReservationStatus.HELD) -> MachineSlot:
    r = res(status, expires_in_min)
    r.id = 7
    return slot_with(r)


def test_confirm_a_live_hold():
    slot = held()
    r = slot.confirm(7, NOW)
    assert r.status == ReservationStatus.CONFIRMED and r.confirmed_at == NOW
    assert slot.reservations[0] is r
    assert not slot.is_available(NOW + timedelta(hours=1))  # a confirmed reservation never lapses


def test_confirm_twice_returns_the_same_reservation_unchanged():
    slot = held()
    first = slot.confirm(7, NOW)
    again = slot.confirm(7, NOW + timedelta(minutes=30))  # even after the hold time is long gone
    assert again is first and again.confirmed_at == NOW


def test_confirm_a_no_show_is_still_the_same_answer():
    assert held(status=ReservationStatus.NO_SHOW).confirm(7, NOW).status == ReservationStatus.NO_SHOW


@pytest.mark.parametrize("expires_in_min", [0, -1])
def test_confirm_at_or_after_expiry_is_hold_expired(expires_in_min):
    slot = held(expires_in_min)
    with pytest.raises(HoldExpired):
        slot.confirm(7, NOW)
    assert slot.reservations[0].status == ReservationStatus.HELD  # refused, nothing changed


def test_confirm_an_expired_hold_is_hold_expired():
    with pytest.raises(HoldExpired):
        held(status=ReservationStatus.EXPIRED).confirm(7, NOW)


def test_confirm_a_cancelled_reservation_is_already_cancelled():
    with pytest.raises(AlreadyCancelled):
        held(status=ReservationStatus.CANCELLED).confirm(7, NOW)


def test_confirm_an_unknown_reservation_is_not_found():
    with pytest.raises(NotFound):
        held().confirm(8, NOW)
