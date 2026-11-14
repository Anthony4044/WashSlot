"""Domain tests: plain objects, no database, microseconds."""
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import ReservationStatus
from app.domain.errors import AlreadyCancelled, HoldExpired, NotFound, SlotUnavailable, TooLateToCancel
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


def test_a_slot_that_already_started_is_not_available():
    past = MachineSlot(
        id=1,
        machine_id=1,
        start_time=NOW - timedelta(minutes=1),
        end_time=NOW + timedelta(hours=1),
    )
    assert not past.is_available(NOW)


def test_place_hold_on_a_past_slot_is_slot_unavailable():
    past = MachineSlot(
        id=1,
        machine_id=1,
        start_time=NOW - timedelta(minutes=1),
        end_time=NOW + timedelta(hours=1),
    )
    with pytest.raises(SlotUnavailable):
        past.place_hold(1, "a@b.c", NOW, minutes=10)


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


# --- place_hold (US-4.1) ----------------------------------------------------------------------
# Plain objects only: the rule is tested here with no database, no HTTP and no lock. The lock that
# stops two requests from running it at the same time is tested in tests/test_hold_race.py.

KIM = 3


def test_place_hold_on_a_free_slot():
    slot = slot_with()
    hold = slot.place_hold(KIM, "kim@example.com", NOW, minutes=10)

    assert hold.status == ReservationStatus.HELD
    assert hold.expires_at == NOW + timedelta(minutes=10)  # 10 minutes from the (database) clock
    assert (hold.slot_id, hold.user_id, hold.confirmation_email) == (1, KIM, "kim@example.com")
    assert hold.id is None  # not saved yet: the repository gives it an id
    assert slot.reservations == [hold]  # it lives inside the aggregate
    assert not slot.is_available(NOW)  # and now it takes the slot


@pytest.mark.parametrize("taken_by", [ReservationStatus.HELD, ReservationStatus.CONFIRMED])
def test_place_hold_on_a_taken_slot_is_slot_unavailable(taken_by):
    slot = slot_with(res(taken_by))
    with pytest.raises(SlotUnavailable):
        slot.place_hold(KIM, "kim@example.com", NOW, minutes=10)
    assert len(slot.reservations) == 1  # refused: nothing was added


@pytest.mark.parametrize("expires_in_min", [0, -1])  # expired exactly now, or a minute ago
def test_a_stale_hold_is_expired_first_and_the_slot_can_be_held(expires_in_min):
    stale = res(ReservationStatus.HELD, expires_in_min)
    slot = slot_with(stale)

    hold = slot.place_hold(KIM, "kim@example.com", NOW, minutes=10)

    assert stale.status == ReservationStatus.EXPIRED  # marked first, so it no longer counts
    assert hold.status == ReservationStatus.HELD
    assert [r for r in slot.reservations if r.is_active(NOW)] == [hold]  # exactly one active


def test_expired_cancelled_and_no_show_reservations_do_not_block_a_hold():
    ended = [res(s) for s in (ReservationStatus.EXPIRED, ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW)]
    hold = slot_with(*ended).place_hold(KIM, "kim@example.com", NOW, minutes=10)
    assert hold.status == ReservationStatus.HELD


def test_the_same_customer_cannot_hold_the_same_slot_twice():
    slot = slot_with()
    slot.place_hold(KIM, "kim@example.com", NOW, minutes=10)
    with pytest.raises(SlotUnavailable):
        slot.place_hold(KIM, "kim@example.com", NOW, minutes=10)


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


# --- cancel (US-5.3) ------------------------------------------------------------------------

def confirmed() -> MachineSlot:
    r = res(ReservationStatus.CONFIRMED, None)
    r.id = 7
    return slot_with(r)


def test_cancel_a_confirmed_reservation_before_start():
    slot = confirmed()
    r = slot.cancel(7, NOW)
    assert r.status == ReservationStatus.CANCELLED and r.cancelled_at == NOW
    assert slot.is_available(NOW)


def test_cancel_a_live_hold_before_start():
    slot = held()
    r = slot.cancel(7, NOW)
    assert r.status == ReservationStatus.CANCELLED
    assert slot.is_available(NOW)


def test_cancel_twice_is_idempotent():
    slot = confirmed()
    first = slot.cancel(7, NOW)
    again = slot.cancel(7, NOW + timedelta(minutes=5))
    assert again is first and again.cancelled_at == NOW


def test_cancel_at_or_after_slot_start_is_too_late():
    slot = confirmed()
    with pytest.raises(TooLateToCancel):
        slot.cancel(7, slot.start_time)
    assert slot.reservations[0].status == ReservationStatus.CONFIRMED


def test_cancel_unknown_reservation_is_not_found():
    with pytest.raises(NotFound):
        confirmed().cancel(8, NOW)
