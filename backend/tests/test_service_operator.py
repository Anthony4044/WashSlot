"""US-7.1: OperatorService on the in-memory unit of work. No HTTP, no database.

The ownership rule is the heart of it: operator:manage only says "you are an operator". Which
laundromat you may touch is checked here, on every use case, and anything else is not_found.
"""
from datetime import UTC, date, datetime

import pytest

from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import MachineType
from app.domain.laundromat import Laundromat
from app.domain.machine import Machine
from app.services.holds import HoldService
from app.services.operator import OperatorService

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)  # 12:00 in Toronto
TOMORROW = date(2030, 1, 8)
OPERATOR, OTHER_OPERATOR = 9, 8
MINE, THEIRS = 1, 2
WASHER, DRYER, THEIR_WASHER = 11, 12, 21


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def uow() -> MemoryUnitOfWork:
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=Clock()))
    uow.laundromats.add(Laundromat(MINE, "Spin City", "1 Main", "America/Toronto", operator_id=OPERATOR))
    uow.laundromats.add(Laundromat(THEIRS, "Fresh Cycle", "2 Main", "America/Toronto", operator_id=OTHER_OPERATOR))
    uow.machines.add(Machine(WASHER, MINE, "Washer 1", MachineType.WASHER, reservable=True))
    uow.machines.add(Machine(DRYER, MINE, "Dryer 1", MachineType.DRYER, reservable=False))
    uow.machines.add(Machine(THEIR_WASHER, THEIRS, "Washer 1", MachineType.WASHER, reservable=True))
    return uow


@pytest.fixture
def service(uow) -> OperatorService:
    return OperatorService(uow)


def create(service, laundromat=MINE, user=OPERATOR, **overrides):
    request = {"from_date": TOMORROW, "to_date": TOMORROW, "open_time": "08:00", "close_time": "12:00",
               "slot_minutes": 60, **overrides}
    return service.create_slots(user, laundromat, **request)


# --- my laundromats and machines ------------------------------------------------------------------

def test_an_operator_sees_only_their_own_laundromats(service):
    outcome = service.list_laundromats(OPERATOR)
    assert [lm.laundromat_id for lm in outcome.value.laundromats] == ["lm_1"]


def test_a_user_who_runs_nothing_sees_an_empty_list(service):
    assert service.list_laundromats(5).value.laundromats == []


def test_the_machine_list_has_every_machine_by_label(service):
    machines = service.list_machines(OPERATOR, MINE).value.machines
    assert [(m.label, m.reservable) for m in machines] == [("Dryer 1", False), ("Washer 1", True)]


# --- the reservable switch --------------------------------------------------------------------------

def test_switching_a_machine_on_is_saved(service, uow):
    outcome = service.set_reservable(OPERATOR, MINE, DRYER, True)

    assert outcome.ok and outcome.value.reservable is True
    assert uow.machines.get(DRYER).reservable is True


def test_the_switch_is_idempotent(service):
    first = service.set_reservable(OPERATOR, MINE, WASHER, True)
    again = service.set_reservable(OPERATOR, MINE, WASHER, True)
    assert first.value == again.value


def test_a_walk_in_only_machine_takes_no_new_hold_and_keeps_old_bookings(service, uow):
    assert create(service, machine_ids=[WASHER]).ok
    slot_id = uow.slots.all_slots()[0].id
    hold = HoldService(uow).place_hold(1, slot_id, "kim@example.com", "kims-attempt")
    assert hold.ok

    service.set_reservable(OPERATOR, MINE, WASHER, False)  # the operator switches the washer off

    # Kim's hold still confirms; a fresh hold on another slot of that washer is refused.
    assert HoldService(uow).confirm(1, int(hold.value.hold_id.removeprefix("hold_"))).ok
    other_slot = uow.slots.all_slots()[1].id
    assert HoldService(uow).place_hold(2, other_slot, "bob@example.com", "bobs-attempt").code == "slot_unavailable"


# --- create slots -------------------------------------------------------------------------------------

def test_create_slots_for_every_reservable_machine(service, uow):
    outcome = create(service)

    assert outcome.value.created == 4 and outcome.value.skipped == 0  # 08-12: 4 slots, washer only (dryer is off)
    assert {s.machine_id for s in uow.slots.all_slots()} == {WASHER}
    assert uow.slots.all_slots()[0].start_time == datetime(2030, 1, 8, 13, 0, tzinfo=UTC)  # 08:00 in Toronto


def test_creating_the_same_slots_again_creates_nothing(service, uow):
    create(service)
    again = create(service)

    assert (again.value.created, again.value.skipped) == (0, 4)
    assert len(uow.slots.all_slots()) == 4


def test_slots_that_already_started_are_skipped(service, uow):
    """Today (in Toronto) from 08:00 to 16:00, and it is 12:00 now: only 13-14, 14-15 and 15-16 are made.

    The 12:00 slot starts this very moment, so it has started too (the same rule as is_available).
    """
    outcome = create(service, from_date=date(2030, 1, 7), to_date=date(2030, 1, 7), close_time="16:00")
    assert (outcome.value.created, outcome.value.skipped) == (3, 5)


def test_a_walk_in_only_machine_can_get_slots_when_named(service, uow):
    outcome = create(service, machine_ids=[DRYER])
    assert outcome.value.created == 4
    assert {s.machine_id for s in uow.slots.all_slots()} == {DRYER}


def test_a_bad_schedule_is_invalid_request(service):
    assert create(service, open_time="12:00", close_time="08:00").code == "invalid_request"


# --- ownership: another operator's things are not_found ----------------------------------------------

@pytest.mark.parametrize("use_case", [
    lambda s: s.list_machines(OPERATOR, THEIRS),
    lambda s: s.set_reservable(OPERATOR, THEIRS, THEIR_WASHER, False),
    lambda s: create(s, laundromat=THEIRS),
    lambda s: s.list_machines(OPERATOR, 999),
], ids=["list-machines", "switch", "create-slots", "unknown-laundromat"])
def test_another_operators_laundromat_is_not_found(service, uow, use_case):
    assert use_case(service).code == "not_found"
    assert uow.machines.get(THEIR_WASHER).reservable is True  # and nothing changed
    assert uow.slots.all_slots() == []


def test_a_machine_of_another_laundromat_is_not_found_even_through_my_own(service, uow):
    """lm_1 is mine, but mch_21 belongs to lm_2: going through my laundromat's URL must not reach it."""
    assert service.set_reservable(OPERATOR, MINE, THEIR_WASHER, False).code == "not_found"
    assert create(service, machine_ids=[THEIR_WASHER]).code == "not_found"
    assert uow.machines.get(THEIR_WASHER).reservable is True
    assert uow.slots.all_slots() == []
