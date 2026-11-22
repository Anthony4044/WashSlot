"""US-7.1 domain rules: the slot schedule, laundromat ownership, and walk-in-only machines. No fixtures."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.enums import ReservationStatus
from app.domain.errors import InvalidSchedule, SlotUnavailable
from app.domain.laundromat import Laundromat
from app.domain.schedule import SlotSchedule
from app.domain.slot import MachineSlot, Reservation

TORONTO = "America/Toronto"
NOW = datetime(2030, 1, 7, 12, 0, tzinfo=UTC)


def schedule(from_day="2030-01-08", to_day="2030-01-08", open_time="08:00", close_time="12:00", minutes=60):
    return SlotSchedule.of(date.fromisoformat(from_day), date.fromisoformat(to_day), open_time, close_time, minutes)


# --- the schedule ---------------------------------------------------------------------------------

def test_slots_run_back_to_back_and_the_last_one_ends_by_closing_time():
    times = schedule(open_time="08:00", close_time="11:30", minutes=60).slot_times(TORONTO)

    # 08-09, 09-10, 10-11 local; 11:00-12:00 would end after 11:30, so it is not made
    assert len(times) == 3
    assert all(end - start == timedelta(hours=1) for start, end in times)
    assert all(times[i][1] == times[i + 1][0] for i in range(len(times) - 1))


def test_times_are_the_laundromats_wall_clock_on_both_sides_of_a_dst_change():
    """Toronto leaves daylight saving time on Sunday 2026-11-01: 08:00 local is 12:00 UTC before, 13:00 after."""
    times = schedule("2026-10-31", "2026-11-02", "08:00", "09:00", 60).slot_times(TORONTO)

    assert [start.astimezone(UTC).hour for start, _ in times] == [12, 13, 13]
    assert all(start.tzinfo is not None for start, _ in times)


def test_closing_at_24_00_means_midnight_at_the_end_of_the_day():
    times = schedule(open_time="22:00", close_time="24:00", minutes=60).slot_times(TORONTO)
    assert len(times) == 2
    assert times[-1][1] - times[0][0] == timedelta(hours=2)


def test_a_range_of_31_days_is_allowed():
    assert len(schedule("2030-01-01", "2030-01-31").days()) == 31


@pytest.mark.parametrize("kwargs", [
    {"from_day": "2030-01-09", "to_day": "2030-01-08"},  # last day before the first
    {"from_day": "2030-01-01", "to_day": "2030-02-01"},  # 32 days
    {"open_time": "12:00", "close_time": "12:00"},  # closes when it opens
    {"open_time": "13:00", "close_time": "12:00"},  # closes before it opens
    {"open_time": "08:00", "close_time": "08:45", "minutes": 60},  # not even one slot fits
    {"minutes": 45},  # not one of the lengths offered
], ids=["backwards", "too-long", "zero-hours", "negative-hours", "nothing-fits", "bad-length"])
def test_a_schedule_that_breaks_the_rules_is_refused(kwargs):
    with pytest.raises(InvalidSchedule) as refused:
        schedule(**kwargs)
    assert refused.value.code == "invalid_request"


# --- ownership --------------------------------------------------------------------------------------

def test_only_the_laundromats_own_operator_runs_it():
    spin_city = Laundromat(id=1, name="Spin City", address="1 Main", timezone=TORONTO, operator_id=9)
    assert spin_city.is_run_by(9)
    assert not spin_city.is_run_by(8)
    assert not Laundromat(id=2, name="New", address="2 Main", timezone=TORONTO).is_run_by(9)  # no operator yet


# --- walk-in-only machines ----------------------------------------------------------------------------

def slot(reservable: bool, reservations=()) -> MachineSlot:
    return MachineSlot(id=1, machine_id=4, start_time=NOW + timedelta(hours=1), end_time=NOW + timedelta(hours=2),
                       reservations=list(reservations), machine_reservable=reservable)


def test_a_walk_in_only_machine_takes_no_new_hold():
    walk_in = slot(reservable=False)
    assert not walk_in.is_available(NOW)
    with pytest.raises(SlotUnavailable):
        walk_in.place_hold(1, "kim@example.com", NOW, minutes=10)


def test_a_hold_made_before_the_switch_can_still_be_confirmed():
    hold = Reservation(id=7, slot_id=1, user_id=1, status=ReservationStatus.HELD, confirmation_email="kim@example.com",
                       expires_at=NOW + timedelta(minutes=5))
    walk_in = slot(reservable=False, reservations=[hold])

    assert walk_in.confirm(7, NOW).status == ReservationStatus.CONFIRMED  # bookings made before stay valid
