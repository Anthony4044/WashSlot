"""Arrival rules, authorization and persistence for US-7.2."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import worker
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import LaundromatRow
from app.domain.enums import ReservationStatus as Status
from app.domain.errors import DomainError, NotFound, TooLateToCheckIn
from app.domain.laundromat import Laundromat
from app.domain.slot import MachineSlot, Reservation
from app.domain.user import OPERATOR_MANAGE, RESERVATIONS_WRITE, User
from app.services.operator import OperatorService
from app.services.reservations import ReservationService
from tests.factories import make_reservation, make_slot, make_user

START = datetime(2030, 1, 7, 23, 55, tzinfo=UTC)
DEADLINE = START + timedelta(minutes=15)
OPERATOR = 9


def make_booking(*, slot_id=1, start=START, status=Status.CONFIRMED, checked_in_at=None):
    reservation = Reservation(
        id=slot_id, slot_id=slot_id, user_id=1, status=status, confirmation_email="delivery@example.com",
        checked_in_at=checked_in_at, created_at=START - timedelta(hours=1),
    )
    return MachineSlot(slot_id, slot_id, start, start + timedelta(hours=1), [reservation])


def test_first_arrival_just_before_deadline_and_retry_after_deadline():
    slot = make_booking()
    arrival = DEADLINE - timedelta(microseconds=1)
    assert slot.check_in(1, arrival).checked_in_at == arrival
    assert slot.check_in(1, DEADLINE).checked_in_at == arrival
    assert slot.mark_no_show(DEADLINE) is False
    assert slot.reservation(1).status == Status.CONFIRMED


def test_unattended_booking_at_the_exact_deadline():
    slot = make_booking()
    assert slot.mark_no_show(DEADLINE - timedelta(microseconds=1)) is False
    with pytest.raises(TooLateToCheckIn):
        slot.check_in(1, DEADLINE)
    assert slot.mark_no_show(DEADLINE) is True
    assert slot.mark_no_show(DEADLINE) is False
    assert slot.active_reservation(DEADLINE) is None
    assert slot.reservation(1).status == Status.NO_SHOW
    assert slot.reservation(1).checked_in_at is None
    # The machine can go to walk-ins for the rest of the slot. Online booking still closes at the start.
    assert slot.is_available(DEADLINE) is False


@pytest.mark.parametrize(("status", "code"), [
    (Status.HELD, "reservation_not_confirmed"),
    (Status.EXPIRED, "reservation_not_confirmed"),
    (Status.CANCELLED, "already_cancelled"),
    (Status.NO_SHOW, "too_late_to_check_in"),
])
def test_only_confirmed_bookings_can_check_in(status, code):
    slot = make_booking(status=status)
    with pytest.raises(DomainError, match=f"^{code}$"):
        slot.check_in(1, START)
    assert slot.mark_no_show(DEADLINE) is False
    assert slot.reservation(1).status == status


def test_unknown_reservation_cannot_check_in():
    with pytest.raises(NotFound):
        make_booking().check_in(2, START)


@pytest.fixture
def store():
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=lambda: DEADLINE))
    uow.users.add(User.register("alice@example.com", "hash"))
    uow.laundromats.add(Laundromat(1, "Spin City", "Main St", "America/Toronto", operator_id=OPERATOR))
    uow.laundromats.add(Laundromat(2, "Fresh Cycle", "First St", "America/Toronto", operator_id=10))
    return uow


def test_service_checks_operator_assignment_and_persists_the_original_timestamp(store):
    store.slots.add(make_booking(start=DEADLINE))
    service = ReservationService(store)
    assert service.check_in(2, 1).code == "not_found"
    assert service.check_in(OPERATOR, 1).code == "not_found"
    assert service.check_in(10, 1, is_operator=True).code == "not_found"

    checked_in = service.check_in(OPERATOR, 1, is_operator=True)
    assert checked_in.ok
    assert checked_in.value.checked_in_at == DEADLINE
    assert service.get(1, 1).value.checked_in_at == DEADLINE
    assert service.check_in(1, 1).value == checked_in.value


def test_service_marks_due_no_shows_but_keeps_bookings_with_arrivals(store):
    store.slots.add(make_booking())
    store.slots.add(make_booking(slot_id=2, checked_in_at=START))
    store.slots.add(make_booking(slot_id=3, start=START + timedelta(seconds=1)))
    service = ReservationService(store)

    assert service.check_in(1, 1).code == "too_late_to_check_in"
    assert service.get(1, 1).value.status == Status.CONFIRMED
    assert service.mark_no_shows() == 1
    assert service.mark_no_shows() == 0
    assert [service.get(1, i).value.status for i in (1, 2, 3)] == [
        Status.NO_SHOW, Status.CONFIRMED, Status.CONFIRMED,
    ]


def test_today_uses_laundromat_day_and_account_email(store):
    # The DB clock reads Jan 8 in UTC, but in Toronto it is still Jan 7.
    store.slots.add(make_booking(slot_id=2, start=START, checked_in_at=START))
    store.slots.add(make_booking(slot_id=1, start=START - timedelta(hours=1), status=Status.NO_SHOW))
    store.slots.add(make_booking(slot_id=3, start=START + timedelta(days=1)))
    store.slots.add(make_booking(slot_id=4, status=Status.CANCELLED))
    store.slots.add(make_booking(slot_id=5, status=Status.HELD))
    service = OperatorService(store)

    assert [lm.laundromat_id for lm in service.list_laundromats(OPERATOR).value.laundromats] == ["lm_1"]
    assert service.today(OPERATOR, 2).code == "not_found"
    today = service.today(OPERATOR, 1).value
    assert today.date.isoformat() == "2030-01-07"
    assert [r.reservation_id for r in today.reservations] == ["res_1", "res_2"]
    assert today.reservations[1].customer_email == "alice@example.com"
    assert today.reservations[1].checked_in_at == START


def test_worker_and_operator_routes_on_postgres(uow_factory, db_session, client, bearer):
    with uow_factory() as uow:
        now = uow.slots.now().astimezone(UTC)
    timezone = ZoneInfo("America/Toronto" if now.hour < 2 or now.hour > 21 else "UTC")
    customer = make_user(db_session)
    operator = make_user(db_session, "operator@example.com")
    laundromat = LaundromatRow(name="Spin City", address="Main St", operator_id=operator.id, timezone=timezone.key)
    db_session.add(laundromat)
    db_session.flush()
    day_start = now.astimezone(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    due_slot = make_slot(db_session, start=now - timedelta(minutes=16), label="Overdue", laundromat=laundromat)
    due = make_reservation(db_session, customer, due_slot, Status.CONFIRMED)
    checked_slot = make_slot(db_session, start=due_slot.start_time, label="Present", laundromat=laundromat)
    present = make_reservation(db_session, customer, checked_slot, Status.CONFIRMED)
    present.checked_in_at = due_slot.start_time
    future_slot = make_slot(db_session, start=day_start + timedelta(days=1), label="Tomorrow", laundromat=laundromat)
    future = make_reservation(db_session, customer, future_slot, Status.CONFIRMED)
    db_session.commit()

    worker.run_due_jobs(uow_factory, {}, now=0)
    db_session.expire_all()
    assert due.status == Status.NO_SHOW
    assert present.status == Status.CONFIRMED
    assert future.status == Status.CONFIRMED
    assert ReservationService(uow_factory).mark_no_shows() == 0

    operator_headers = bearer(operator.id, scopes=(OPERATOR_MANAGE, RESERVATIONS_WRITE))
    response = client.post(f"/reservations/res_{future.id}/check-in", headers=operator_headers)
    assert response.status_code == 200
    assert response.json()["checkedInAt"]
    operator_view = client.get(f"/operator/laundromats/lm_{laundromat.id}/today", headers=operator_headers)
    assert operator_view.status_code == 200
    rows = operator_view.json()["reservations"]
    assert [r["reservationId"] for r in rows] == [f"res_{due.id}", f"res_{present.id}"]
    assert [(r["status"], r["checkedInAt"] is not None) for r in rows] == [("NO_SHOW", False), ("CONFIRMED", True)]
