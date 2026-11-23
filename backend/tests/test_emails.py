"""US-6.1: the confirmation email, sent through an outbox so it survives Resend being down.

What we prove:
- confirming writes ONE outbox message, in the same unit of work (a repeat or a refusal writes none)
- the worker sends it; failures are retried at 30 s, 1 m, ...; after 6 tries it is FAILED
- a 4xx from Resend is FAILED right away; the reservation stays CONFIRMED whatever happens
- the Resend client sends the Idempotency-Key and sorts errors into "retry" and "give up"
- EMAIL_FAKE_FAILURES makes the first N sends fail
"""
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.email import EmailSendError, ResendEmailSender
from app.core.logging import correlation_context, correlation_id
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import NotificationOutboxRow
from app.domain.enums import OutboxStatus, ReservationStatus
from app.domain.notification import MAX_ATTEMPTS
from app.domain.slot import MachineSlot, Reservation
from app.services.emails import EmailService, confirmation_text
from app.services.holds import HoldService
from app.services.reservations import ReservationService
from tests.factories import make_reservation, make_slot, make_user

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)
ALICE = 1


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class FakeSender:
    """Stands in for Resend. `fail_with` is a list of errors to raise, one per send, then success."""

    def __init__(self, fail_with: list[EmailSendError] | None = None):
        self.fail_with = list(fail_with or [])
        self.sent: list[dict] = []  # emails that "arrived"
        self.tries = 0

    def send(self, to, subject, text, idempotency_key):
        self.tries += 1
        if self.fail_with:
            raise self.fail_with.pop(0)
        self.sent.append({"to": to, "subject": subject, "text": text, "key": idempotency_key})


def down() -> EmailSendError:
    return EmailSendError("Resend answered 503", retryable=True)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    return MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))


def confirmed_hold(uow, *, correlation_id=None) -> int:
    """Alice holds slot 1 and confirms it. Returns the reservation id."""
    uow.slots.add(MachineSlot(id=1, machine_id=4, start_time=NOW + timedelta(hours=2),
                              end_time=NOW + timedelta(hours=3)))
    slot = uow.slots.get(1)
    slot.reservations.append(Reservation(id=None, slot_id=1, user_id=ALICE, status=ReservationStatus.HELD,
                                         confirmation_email="alice@example.com",
                                         expires_at=NOW + timedelta(minutes=10)))
    uow.slots.save(slot)
    hold_id = slot.reservations[0].id
    assert HoldService(uow).confirm(ALICE, hold_id, correlation_id=correlation_id).ok
    return hold_id


def only_message(uow):
    [message] = uow.outbox.messages.values()
    return message


# --- Confirm writes the outbox message -------------------------------------------------------

def test_confirm_writes_one_pending_email(uow):
    reservation_id = confirmed_hold(uow)
    message = only_message(uow)
    assert message.status == OutboxStatus.PENDING and message.reservation_id == reservation_id
    assert message.payload["to"] == "alice@example.com" and message.payload["machineLabel"] == "Washer 4"


def test_confirming_again_does_not_write_a_second_email(uow):
    reservation_id = confirmed_hold(uow, correlation_id="original-confirm")
    assert HoldService(uow).confirm(ALICE, reservation_id, correlation_id="repeat-confirm").ok
    assert len(uow.outbox.messages) == 1
    assert only_message(uow).correlation_id == "original-confirm"


def test_a_refused_confirm_writes_no_email(uow, clock):
    uow.slots.add(MachineSlot(id=1, machine_id=4, start_time=NOW + timedelta(hours=2),
                              end_time=NOW + timedelta(hours=3)))
    slot = uow.slots.get(1)
    slot.reservations.append(Reservation(id=None, slot_id=1, user_id=ALICE, status=ReservationStatus.HELD,
                                         confirmation_email="alice@example.com",
                                         expires_at=NOW - timedelta(minutes=1)))  # already expired
    uow.slots.save(slot)
    assert HoldService(uow).confirm(ALICE, slot.reservations[0].id).code == "hold_expired"
    assert uow.outbox.messages == {}


# --- The worker sends it ------------------------------------------------------------------------

def test_the_worker_sends_the_email_once(uow):
    confirmed_hold(uow)
    sender = FakeSender()
    assert EmailService(uow, sender).send_due_emails() == 1
    assert EmailService(uow, sender).send_due_emails() == 0  # nothing left to send

    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == "alice@example.com"
    assert sender.sent[0]["key"] == f"outbox-{only_message(uow).id}"  # Resend's Idempotency-Key
    assert only_message(uow).status == OutboxStatus.SENT
    assert only_message(uow).correlation_id == f"outbox-{only_message(uow).id}"


def test_worker_and_sender_keep_the_stored_id_through_retries(uow, clock, json_logs):
    reservation_id = confirmed_hold(uow, correlation_id="confirmation-trace")
    sender = ResendEmailSender(api_key=None, from_address="test@example.com", fake_failures=1)
    with correlation_context("outer"):
        assert EmailService(uow, sender).send_due_emails() == 0
        assert correlation_id.get() == "outer"
        assert only_message(uow).correlation_id == "confirmation-trace"
        clock.now += timedelta(seconds=30)
        assert EmailService(uow, sender).send_due_emails() == 1
        assert correlation_id.get() == "outer"

    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    deliveries = [entry for entry in entries if entry["logger"] == "app.services.emails"]
    transport = [entry for entry in entries if entry["logger"] == "app.core.email"]
    assert len(deliveries) == 4 and len(transport) == 1
    assert all(entry["correlationId"] == "confirmation-trace" for entry in deliveries + transport)
    assert all(entry["reservationId"] == reservation_id for entry in deliveries)
    assert [entry["attempt"] for entry in deliveries] == [1, 1, 2, 2]
    assert correlation_id.get() is None


def test_unexpected_delivery_failure_logs_the_id_and_clears_context(uow, json_logs):
    confirmed_hold(uow, correlation_id="crashed-delivery")

    class BrokenSender:
        def send(self, *args, **kwargs):
            raise RuntimeError("unexpected sender failure")

    with pytest.raises(RuntimeError, match="unexpected sender failure"):
        EmailService(uow, BrokenSender()).send_due_emails()
    assert correlation_id.get() is None
    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    failure = next(entry for entry in entries if entry["message"] == "email delivery failed")
    assert failure["correlationId"] == "crashed-delivery"
    assert "RuntimeError" in failure["exception"]


def test_fails_twice_then_sent(uow, clock):
    reservation_id = confirmed_hold(uow)
    sender = FakeSender(fail_with=[down(), down()])
    service = EmailService(uow, sender)

    service.send_due_emails()  # try 1 fails -> next try in 30 s
    assert only_message(uow).next_attempt_at == NOW + timedelta(seconds=30)

    clock.now += timedelta(seconds=10)
    service.send_due_emails()  # too early: nothing is tried
    assert sender.tries == 1

    clock.now = NOW + timedelta(seconds=30)
    service.send_due_emails()  # try 2 fails -> next try 1 minute later
    clock.now += timedelta(minutes=1)
    service.send_due_emails()  # try 3 works

    message = only_message(uow)
    assert message.status == OutboxStatus.SENT and message.attempts == 3 and len(sender.sent) == 1
    assert ReservationService(uow).get(ALICE, reservation_id).value.status == ReservationStatus.CONFIRMED


def test_always_failing_ends_as_failed_after_6_tries(uow, clock):
    reservation_id = confirmed_hold(uow)
    sender = FakeSender(fail_with=[down() for _ in range(100)])
    service = EmailService(uow, sender)
    for _ in range(10):  # more rounds than needed; each one jumps past the longest wait
        service.send_due_emails()
        clock.now += timedelta(minutes=10)

    message = only_message(uow)
    assert message.status == OutboxStatus.FAILED
    assert message.attempts == MAX_ATTEMPTS == sender.tries == 6
    assert "503" in message.last_error
    # The email failed, but the booking did not: it stays CONFIRMED.
    assert ReservationService(uow).get(ALICE, reservation_id).value.status == ReservationStatus.CONFIRMED


def test_a_4xx_is_failed_right_away(uow):
    confirmed_hold(uow)
    sender = FakeSender(fail_with=[EmailSendError("Resend answered 422: bad address", retryable=False)])
    EmailService(uow, sender).send_due_emails()
    message = only_message(uow)
    assert message.status == OutboxStatus.FAILED and message.attempts == 1


def test_the_email_text_uses_the_laundromat_local_time():
    subject, text = confirmation_text({
        "to": "a@example.com", "laundromatName": "Spin City", "laundromatAddress": "1 Main St",
        "machineLabel": "Washer 4", "machineType": "WASHER",
        "startTime": "2026-11-27T23:00:00+00:00", "endTime": "2026-11-28T00:00:00+00:00",
        "timezone": "America/Toronto",
    })
    assert subject == "WashSlot: Washer 4 is yours on Friday, November 27 at 18:00"
    assert "Spin City, 1 Main St" in text and "18:00 to 19:00" in text and "Washer 4 (washer)" in text


# --- The Resend client --------------------------------------------------------------------------

def resend_answering(status: int, seen: list | None = None) -> ResendEmailSender:
    """A ResendEmailSender whose HTTP calls go to a fake Resend that answers `status`."""
    def fake_resend(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"id": "email_1"})

    return ResendEmailSender("re_test_key", "WashSlot <onboarding@resend.dev>",
                             http=httpx.Client(transport=httpx.MockTransport(fake_resend)))


def test_resend_gets_the_key_and_the_idempotency_key():
    seen = []
    resend_answering(200, seen).send("a@example.com", "Hi", "Body", idempotency_key="outbox-7")
    assert seen[0].headers["Authorization"] == "Bearer re_test_key"
    assert seen[0].headers["Idempotency-Key"] == "outbox-7"


@pytest.mark.parametrize(("status", "retryable"), [(500, True), (503, True), (429, True), (422, False), (401, False)])
def test_resend_errors_are_sorted_into_retry_or_give_up(status, retryable):
    with pytest.raises(EmailSendError) as raised:
        resend_answering(status).send("a@example.com", "Hi", "Body", idempotency_key="outbox-7")
    assert raised.value.retryable is retryable


def test_a_network_error_is_retryable():
    def no_network(request):
        raise httpx.ConnectError("no route to host")

    sender = ResendEmailSender("re_test_key", "x@example.com",
                               http=httpx.Client(transport=httpx.MockTransport(no_network)))
    with pytest.raises(EmailSendError) as raised:
        sender.send("a@example.com", "Hi", "Body", idempotency_key="outbox-7")
    assert raised.value.retryable is True


def test_fake_failures_switch_fails_the_first_n_sends():
    sender = ResendEmailSender(api_key=None, from_address="x@example.com", fake_failures=2)
    for _ in range(2):
        with pytest.raises(EmailSendError):
            sender.send("a@example.com", "Hi", "Body", idempotency_key="outbox-1")
    sender.send("a@example.com", "Hi", "Body", idempotency_key="outbox-1")  # 3rd works (logged, no key)


# --- On the real database -----------------------------------------------------------------------

@pytest.mark.parametrize("supplied_id", [None, "booking-db-trace"])
def test_confirm_on_the_database_writes_the_outbox_row(client, db_session, bearer, supplied_id):
    user, slot = make_user(db_session), make_slot(db_session)
    hold = make_reservation(db_session, user, slot)
    db_session.commit()

    headers = bearer(user.id)
    if supplied_id is not None:
        headers["X-Correlation-ID"] = supplied_id
    response = client.post(f"/holds/hold_{hold.id}/confirm", headers=headers)
    assert response.status_code == 200

    [row] = db_session.scalars(select(NotificationOutboxRow)).all()
    assert row.reservation_id == hold.id and row.status == OutboxStatus.PENDING
    assert row.payload["laundromatName"] == "Spin City" and row.payload["timezone"] == "America/Toronto"
    assert row.correlation_id == response.headers["X-Correlation-ID"]
    if supplied_id is not None:
        assert row.correlation_id == supplied_id


def test_the_worker_sends_and_records_on_the_database(client, db_session, bearer, uow_factory, json_logs):
    user, slot = make_user(db_session), make_slot(db_session)
    hold = make_reservation(db_session, user, slot)
    db_session.commit()
    headers = {**bearer(user.id), "X-Correlation-ID": "db-worker-trace"}
    client.post(f"/holds/hold_{hold.id}/confirm", headers=headers)

    sender = FakeSender(fail_with=[down()])
    EmailService(uow_factory, sender).send_due_emails()  # fails once, waits 30 s

    db_session.expire_all()
    row = db_session.scalars(select(NotificationOutboxRow)).one()
    assert row.status == OutboxStatus.PENDING and row.attempts == 1 and "503" in row.last_error
    assert EmailService(uow_factory, sender).send_due_emails() == 0  # not due yet
    assert row.correlation_id == "db-worker-trace"
    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    api_log = next(entry for entry in entries if entry["message"] == "request completed")
    worker_logs = [entry for entry in entries if entry["logger"] == "app.services.emails"]
    assert worker_logs
    assert api_log["correlationId"] == "db-worker-trace"
    assert all(entry["correlationId"] == api_log["correlationId"] for entry in worker_logs)
    assert all(entry["reservationId"] == hold.id for entry in worker_logs)


def test_two_workers_never_claim_the_same_message(db_session, uow_factory):
    """FOR UPDATE SKIP LOCKED: while worker A holds its claim open, worker B gets the OTHER message."""
    user = make_user(db_session)
    for label in ("W1", "W2"):
        slot = make_slot(db_session, label=label)
        reservation = make_reservation(db_session, user, slot, ReservationStatus.CONFIRMED)
        db_session.add(NotificationOutboxRow(
            reservation_id=reservation.id, laundromat_id=1, type="SEND_CONFIRMATION_EMAIL",
            payload={}, status=OutboxStatus.PENDING, next_attempt_at=datetime.now(UTC) - timedelta(minutes=1)))
    db_session.commit()

    with uow_factory() as worker_a:
        claimed_by_a = worker_a.outbox.claim_next()  # A's transaction is still open (row locked)
        with uow_factory() as worker_b:
            claimed_by_b = worker_b.outbox.claim_next()
    assert claimed_by_a is not None and claimed_by_b is not None
    assert claimed_by_a.id != claimed_by_b.id
