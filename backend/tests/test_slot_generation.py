"""Availability rolls forward with the database clock, including after worker downtime."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

import worker
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import MachineSlotRow
from app.domain.enums import MachineType
from app.domain.laundromat import Laundromat
from app.domain.machine import Machine
from app.domain.slot import MachineSlot
from app.services.holds import HoldService
from app.services.slot_generation import maintain_slot_window
from tests.factories import make_slot

TORONTO = ZoneInfo("America/Toronto")


@pytest.fixture
def clock():
    return SimpleNamespace(now=datetime(2030, 1, 7, 17, tzinfo=UTC))  # noon in Toronto


@pytest.fixture
def uow(clock):
    store = MemoryUnitOfWork(slots=MemorySlotRepository(clock=lambda: clock.now))
    store.laundromats.add(Laundromat(1, "Spin City", "1 Main", "America/Toronto"))
    store.machines.add(Machine(1, 1, "Washer 1", MachineType.WASHER, True))
    store.machines.add(Machine(2, 1, "Washer 2", MachineType.WASHER, False))
    return store


def test_generates_seven_days_and_skips_started_slots(uow, clock):
    assert maintain_slot_window(uow) == 7 + 6 * 12
    slots = uow.slots.all_slots()
    assert {slot.machine_id for slot in slots} == {1}
    assert all(slot.start_time > clock.now for slot in slots)
    days = {slot.start_time.astimezone(TORONTO).date() for slot in slots}
    assert days == {date(2030, 1, 7) + timedelta(days=offset) for offset in range(7)}
    assert all(8 <= slot.start_time.astimezone(TORONTO).hour < 20 for slot in slots)


def test_repeat_is_idempotent_and_next_day_extends_the_window(uow, clock):
    maintain_slot_window(uow)
    before = uow.slots.all_slots()
    assert maintain_slot_window(uow) == 0
    assert uow.slots.all_slots() == before
    clock.now += timedelta(days=1)
    assert maintain_slot_window(uow) == 12
    assert max(slot.start_time.astimezone(TORONTO).date() for slot in uow.slots.all_slots()) == date(2030, 1, 14)


def test_worker_catches_up_after_missing_several_days(uow, clock):
    maintain_slot_window(uow)
    clock.now += timedelta(days=20)
    assert maintain_slot_window(uow) == 7 + 6 * 12
    latest = max(slot.start_time for slot in uow.slots.all_slots()).astimezone(TORONTO).date()
    assert latest == clock.now.astimezone(TORONTO).date() + timedelta(days=6)


def test_existing_custom_day_and_booking_are_preserved(uow):
    start = datetime(2030, 1, 8, 15, 15, tzinfo=UTC)
    custom = MachineSlot(1, 1, start, start + timedelta(minutes=30))
    uow.slots.add(custom)
    held = HoldService(uow).place_hold(1, custom.id, "alice@example.com", "generation-test-hold")
    assert held.ok
    before = uow.slots.get(custom.id)
    maintain_slot_window(uow)
    assert uow.slots.get(custom.id) == before
    assert [slot for slot in uow.slots.all_slots() if slot.start_time.astimezone(TORONTO).date()
            == date(2030, 1, 8)] == [before]


def test_each_laundromat_uses_its_local_date(uow, clock):
    clock.now = datetime(2030, 1, 7, 1, tzinfo=UTC)  # January 6 in Toronto, January 7 in Tokyo
    uow.laundromats.add(Laundromat(2, "Tokyo Laundry", "2 Main", "Asia/Tokyo"))
    uow.machines.add(Machine(3, 2, "Washer 3", MachineType.WASHER, True))
    maintain_slot_window(uow)
    slots = uow.slots.all_slots()
    tokyo = [slot for slot in slots if slot.machine_id == 3]
    assert min(slot.start_time.astimezone(ZoneInfo("Asia/Tokyo")).date() for slot in tokyo) == date(2030, 1, 7)
    toronto_days = [slot.start_time.astimezone(TORONTO).date() for slot in slots if slot.machine_id == 1]
    assert max(toronto_days) == date(2030, 1, 12)
    assert maintain_slot_window(uow) == 0


def test_opening_hours_follow_daylight_saving_time(uow, clock):
    clock.now = datetime(2026, 10, 31, 10, tzinfo=UTC)
    maintain_slot_window(uow)
    openings = {slot.start_time.astimezone(TORONTO).date(): slot.start_time
                for slot in uow.slots.all_slots() if slot.start_time.astimezone(TORONTO).hour == 8}
    assert openings[date(2026, 10, 31)].hour == 12
    assert openings[date(2026, 11, 1)].hour == 13


def test_worker_runs_generation_on_startup_and_again_hourly(uow, clock, monkeypatch):
    monkeypatch.setattr(worker, "JOBS", [job for job in worker.JOBS if job[0] == "generate upcoming slots"])
    next_run = {}
    worker.run_due_jobs(uow, next_run, now=0)
    assert uow.slots.all_slots()
    clock.now += timedelta(days=1)
    count = len(uow.slots.all_slots())
    worker.run_due_jobs(uow, next_run, now=3599)
    assert len(uow.slots.all_slots()) == count
    worker.run_due_jobs(uow, next_run, now=3600)
    assert len(uow.slots.all_slots()) == count + 12


def test_concurrent_workers_and_custom_slots_on_postgres(db_session, uow_factory):
    custom = make_slot(db_session)
    custom.start_time = (datetime.now(TORONTO) + timedelta(days=1)).replace(
        hour=10, minute=15, second=0, microsecond=0,
    )
    custom.end_time = custom.start_time + timedelta(minutes=30)
    db_session.commit()
    day_start = custom.start_time.replace(hour=0, minute=0)
    machine_id = custom.machine_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: maintain_slot_window(uow_factory), range(2)))
    assert sum(count > 0 for count in results) == 1
    assert maintain_slot_window(uow_factory) == 0
    count = db_session.scalar(select(func.count()).select_from(MachineSlotRow).where(
        MachineSlotRow.machine_id == machine_id,
        MachineSlotRow.start_time >= day_start,
        MachineSlotRow.start_time < day_start + timedelta(days=1),
    ))
    assert count == 1
