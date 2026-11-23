"""US-7.3: an operator sees which confirmation emails failed and sends them again.

What we prove (T.7.3.3):
- retry is a domain rule: FAILED goes back to PENDING with attempts 0, due now; PENDING and SENT are
  left alone, so retrying twice never emails the customer twice
- an operator lists only their own laundromats' emails, and ?status filters them
- another laundromat's email is 404 (the list never shows it, retry can't touch it); customers get 403
- "done when": after a retry the worker really sends it, and the email ends SENT
- on the database: the same, plus the retry locks the row (FOR UPDATE)
"""
import copy
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.api.deps import get_uow_factory
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import LaundromatRow, NotificationOutboxRow
from app.domain.enums import OutboxStatus, ReservationStatus, UserRole
from app.domain.laundromat import Laundromat
from app.domain.notification import CONFIRMATION_EMAIL, MAX_ATTEMPTS, OutboxMessage
from app.domain.user import SCOPES_BY_ROLE
from app.main import app
from app.services.emails import EmailService
from app.services.operator import OperatorService
from tests.conformance.contract import check, check_error
from tests.factories import make_reservation, make_slot, make_user

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)
OPERATOR, OTHER_OPERATOR, CUSTOMER = 9, 8, 1
MINE, THEIRS = 1, 2
OPERATOR_SCOPES = SCOPES_BY_ROLE[UserRole.OPERATOR]
LIST = "/operator/notifications"
RETRY = "/operator/notifications/{notificationId}/retry"


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class FakeSender:
    """Stands in for Resend: every send arrives."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to, subject, text, idempotency_key):
        self.sent.append({"to": to, "key": idempotency_key})


def payload(to: str = "kim@example.com", start: datetime = NOW + timedelta(days=1)) -> dict:
    """What confirm writes (domain/notification.py confirmation_email)."""
    return {"to": to, "laundromatName": "Spin City", "laundromatAddress": "1 Main St", "machineLabel": "Washer 1",
            "machineType": "WASHER", "startTime": start.isoformat(),
            "endTime": (start + timedelta(hours=1)).isoformat(), "timezone": "America/Toronto"}


def message(status: OutboxStatus = OutboxStatus.FAILED, laundromat_id: int = MINE, **fields) -> OutboxMessage:
    attempts = {OutboxStatus.FAILED: MAX_ATTEMPTS, OutboxStatus.SENT: 1}.get(status, 0)
    return OutboxMessage(**{
        "id": None, "reservation_id": 70, "laundromat_id": laundromat_id, "type": CONFIRMATION_EMAIL,
        "payload": payload(), "next_attempt_at": NOW - timedelta(hours=1), "status": status,
        "attempts": attempts, "last_error": "Resend answered 503" if status == OutboxStatus.FAILED else None,
        **fields,
    })


# --- the domain rule ----------------------------------------------------------------------------

def test_retry_puts_a_failed_email_back_in_the_queue():
    email = message(OutboxStatus.FAILED)

    assert email.retry(NOW) is True
    assert (email.status, email.attempts, email.next_attempt_at) == (OutboxStatus.PENDING, 0, NOW)
    assert email.last_error == "Resend answered 503"  # kept until the next try, so the operator sees why


@pytest.mark.parametrize("status", [OutboxStatus.PENDING, OutboxStatus.SENT])
def test_retry_leaves_a_pending_or_sent_email_alone(status):
    email = message(status)
    before = copy.deepcopy(email)

    assert email.retry(NOW) is False
    assert email == before  # SENT already arrived: sending it again would email the customer twice


def test_a_retried_email_gets_six_fresh_tries():
    email = message(OutboxStatus.FAILED)
    email.retry(NOW)

    for _ in range(MAX_ATTEMPTS - 1):
        email.mark_failed_try("Resend answered 503", retryable=True, now=NOW)
    assert email.status == OutboxStatus.PENDING  # 5 failed tries: still trying, with the usual backoff
    email.mark_failed_try("Resend answered 503", retryable=True, now=NOW)
    assert email.status == OutboxStatus.FAILED and email.attempts == MAX_ATTEMPTS


# --- the use cases, in memory --------------------------------------------------------------------

@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    """Laundromat 1 is run by operator 9, laundromat 2 by operator 8."""
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))
    uow.laundromats.add(Laundromat(MINE, "Spin City", "1 Main St", "America/Toronto", operator_id=OPERATOR))
    uow.laundromats.add(Laundromat(THEIRS, "Fresh Cycle", "2 Main St", "America/Toronto", operator_id=OTHER_OPERATOR))
    return uow


def add(uow, clock, email: OutboxMessage) -> int:
    """Store the email one minute after the previous one (so 'newest first' has an order). Returns its id."""
    clock.now += timedelta(minutes=1)
    uow.outbox.add(email)
    return email.id


def test_an_operator_lists_only_their_own_laundromats_emails_newest_first(uow, clock):
    old = add(uow, clock, message(OutboxStatus.FAILED))
    add(uow, clock, message(OutboxStatus.FAILED, laundromat_id=THEIRS))
    new = add(uow, clock, message(OutboxStatus.SENT))

    listed = OperatorService(uow).list_notifications(OPERATOR).value.notifications

    assert [n.notification_id for n in listed] == [f"ntf_{new}", f"ntf_{old}"]
    assert {n.laundromat_name for n in listed} == {"Spin City"}


def test_the_status_filter_keeps_only_that_status(uow, clock):
    failed = add(uow, clock, message(OutboxStatus.FAILED))
    add(uow, clock, message(OutboxStatus.PENDING))
    add(uow, clock, message(OutboxStatus.SENT))

    listed = OperatorService(uow).list_notifications(OPERATOR, OutboxStatus.FAILED).value.notifications

    assert [(n.notification_id, n.status) for n in listed] == [(f"ntf_{failed}", OutboxStatus.FAILED)]
    assert listed[0].last_error == "Resend answered 503" and listed[0].recipient == "kim@example.com"


def test_a_user_who_runs_no_laundromat_sees_no_emails(uow, clock):
    add(uow, clock, message(OutboxStatus.FAILED))
    assert OperatorService(uow).list_notifications(5).value.notifications == []


def test_retry_saves_the_email_as_pending_and_due_now(uow, clock):
    email_id = add(uow, clock, message(OutboxStatus.FAILED))

    outcome = OperatorService(uow).retry_notification(OPERATOR, email_id)

    assert outcome.ok and outcome.value.status == OutboxStatus.PENDING and outcome.value.next_attempt_at == clock.now
    stored = uow.outbox.messages[email_id]
    assert (stored.status, stored.attempts, stored.next_attempt_at) == (OutboxStatus.PENDING, 0, clock.now)


def test_retrying_twice_is_the_same_as_once(uow, clock):
    email_id = add(uow, clock, message(OutboxStatus.FAILED))
    first = OperatorService(uow).retry_notification(OPERATOR, email_id)
    clock.now += timedelta(seconds=1)  # the double click arrives a moment later

    again = OperatorService(uow).retry_notification(OPERATOR, email_id)

    assert again.ok and again.value == first.value  # still PENDING, still due at the first retry's time


@pytest.mark.parametrize("email", [
    message(OutboxStatus.FAILED, laundromat_id=THEIRS),  # another operator's laundromat
    None,  # no such email at all
], ids=["another-laundromats-email", "unknown-id"])
def test_retrying_an_email_that_isnt_mine_is_not_found(uow, clock, email):
    email_id = add(uow, clock, email) if email else 999
    before = copy.deepcopy(uow.outbox.messages)

    assert OperatorService(uow).retry_notification(OPERATOR, email_id).code == "not_found"
    assert uow.outbox.messages == before  # and nothing changed


def test_done_when_a_retried_email_gets_sent(uow, clock):
    email_id = add(uow, clock, message(OutboxStatus.FAILED))
    sender = FakeSender()
    assert EmailService(uow, sender).send_due_emails() == 0  # FAILED: the worker leaves it alone

    OperatorService(uow).retry_notification(OPERATOR, email_id)

    assert EmailService(uow, sender).send_due_emails() == 1
    assert uow.outbox.messages[email_id].status == OutboxStatus.SENT
    assert sender.sent == [{"to": "kim@example.com", "key": f"outbox-{email_id}"}]  # same Resend key as before


def test_retrying_a_sent_email_never_sends_it_again(uow, clock):
    email_id = add(uow, clock, message(OutboxStatus.SENT))
    sender = FakeSender()

    assert OperatorService(uow).retry_notification(OPERATOR, email_id).value.status == OutboxStatus.SENT
    assert EmailService(uow, sender).send_due_emails() == 0 and sender.sent == []


# --- through HTTP, every response checked against the contract ---------------------------------

@pytest.fixture
def memory_client(api_client, uow, clock) -> Iterator[TestClient]:
    """Email 1: laundromat 1's FAILED email. Email 2: laundromat 2's FAILED email."""
    add(uow, clock, message(OutboxStatus.FAILED))
    add(uow, clock, message(OutboxStatus.FAILED, laundromat_id=THEIRS))
    app.dependency_overrides[get_uow_factory] = lambda: uow
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


EVERY_OPERATION = [("get", LIST, "/operator/notifications?status=FAILED"),
                   ("post", RETRY, "/operator/notifications/ntf_1/retry")]
IDS = ["listOperatorNotifications", "retryNotification"]


@pytest.mark.parametrize(("method", "path", "url"), EVERY_OPERATION, ids=IDS)
def test_no_token_is_401(memory_client, method, path, url):
    check_error(memory_client.request(method.upper(), url), path, method, 401, "missing_token")


@pytest.mark.parametrize(("method", "path", "url"), EVERY_OPERATION, ids=IDS)
def test_customers_get_403(memory_client, uow, bearer, method, path, url):
    r = memory_client.request(method.upper(), url, headers=bearer(CUSTOMER))  # no operator:manage

    check_error(r, path, method, 403, "insufficient_scope")
    assert uow.outbox.messages[1].status == OutboxStatus.FAILED  # nothing changed


def test_the_list_shows_my_failed_email_only(memory_client, bearer):
    r = memory_client.get("/operator/notifications?status=FAILED", headers=bearer(OPERATOR, OPERATOR_SCOPES))

    [email] = check(r, LIST, "get")["notifications"]
    assert email["notificationId"] == "ntf_1" and email["laundromatId"] == "lm_1"
    assert email["status"] == "FAILED" and email["nextAttemptAt"] is None


def test_an_unknown_status_is_422(memory_client, bearer):
    r = memory_client.get("/operator/notifications?status=LOST", headers=bearer(OPERATOR, OPERATOR_SCOPES))
    check_error(r, LIST, "get", 422, "invalid_request")


def test_retry_answers_the_email_as_pending(memory_client, bearer):
    r = memory_client.post("/operator/notifications/ntf_1/retry", headers=bearer(OPERATOR, OPERATOR_SCOPES))

    email = check(r, RETRY, "post")
    assert (email["status"], email["attempts"]) == ("PENDING", 0) and email["nextAttemptAt"] is not None


@pytest.mark.parametrize("url", [
    "/operator/notifications/ntf_2/retry",  # laundromat 2's email
    "/operator/notifications/ntf_404/retry",  # no such email
    "/operator/notifications/res_1/retry",  # not a notification id
], ids=["theirs", "unknown", "wrong-prefix"])
def test_retrying_someone_elses_email_is_404(memory_client, uow, bearer, url):
    r = memory_client.post(url, headers=bearer(OPERATOR, OPERATOR_SCOPES))

    check_error(r, RETRY, "post", 404, "not_found")
    assert uow.outbox.messages[2].status == OutboxStatus.FAILED  # laundromat 2's email is untouched


# --- on the database ------------------------------------------------------------------------------

@pytest.fixture
def failed_emails(db_session):
    """Two laundromats, each with a confirmed booking whose email FAILED. Returns (operator, mine, theirs)."""
    operator, other = make_user(db_session, "operator@example.com"), make_user(db_session, "other@example.com")
    kim = make_user(db_session, "kim@example.com")
    rows = []
    for owner, name in ((operator, "Spin City"), (other, "Fresh Cycle")):
        laundromat = LaundromatRow(name=name, address="1 Main St", operator_id=owner.id)
        db_session.add(laundromat)
        db_session.flush()
        slot = make_slot(db_session, laundromat=laundromat)
        reservation = make_reservation(db_session, kim, slot, ReservationStatus.CONFIRMED)
        row = NotificationOutboxRow(
            reservation_id=reservation.id, laundromat_id=laundromat.id, type=CONFIRMATION_EMAIL,
            payload=payload(start=slot.start_time), status=OutboxStatus.FAILED, attempts=MAX_ATTEMPTS,
            next_attempt_at=datetime.now(UTC) - timedelta(hours=1), last_error="Resend answered 503")
        db_session.add(row)
        rows.append(row)
    db_session.commit()
    return operator, rows[0], rows[1]


def test_on_the_database_an_operator_lists_and_retries_only_their_own(client, db_session, bearer, failed_emails):
    operator, mine, theirs = failed_emails
    headers = bearer(operator.id, OPERATOR_SCOPES)

    listed = check(client.get("/operator/notifications", params={"status": "FAILED"}, headers=headers), LIST, "get")
    retried = client.post(f"/operator/notifications/ntf_{mine.id}/retry", headers=headers)
    refused = client.post(f"/operator/notifications/ntf_{theirs.id}/retry", headers=headers)

    assert [n["notificationId"] for n in listed["notifications"]] == [f"ntf_{mine.id}"]
    assert check(retried, RETRY, "post")["status"] == "PENDING"
    check_error(refused, RETRY, "post", 404, "not_found")
    db_session.expire_all()
    saved, untouched = db_session.get(NotificationOutboxRow, mine.id), db_session.get(NotificationOutboxRow, theirs.id)
    assert (saved.status, saved.attempts) == (OutboxStatus.PENDING, 0)  # really saved
    assert saved.next_attempt_at <= datetime.now(UTC)  # due now, by the database clock
    assert (untouched.status, untouched.attempts) == (OutboxStatus.FAILED, MAX_ATTEMPTS)


def test_on_the_database_the_retried_email_is_sent(client, db_session, bearer, uow_factory, failed_emails):
    operator, mine, _ = failed_emails
    client.post(f"/operator/notifications/ntf_{mine.id}/retry", headers=bearer(operator.id, OPERATOR_SCOPES))

    sender = FakeSender()
    assert EmailService(uow_factory, sender).send_due_emails() == 1  # only mine: theirs is still FAILED

    db_session.expire_all()
    assert db_session.scalar(select(NotificationOutboxRow.status).where(NotificationOutboxRow.id == mine.id)) \
        == OutboxStatus.SENT
    assert sender.sent == [{"to": "kim@example.com", "key": f"outbox-{mine.id}"}]


def test_on_the_database_a_retry_locks_the_email_row(uow_factory, failed_emails):
    """While one retry holds the row (FOR UPDATE, not committed yet), a second one can't read it to
    change it: it waits. Here it gives up after 100 ms instead of waiting, to prove the lock is there."""
    _, mine, _ = failed_emails
    with uow_factory() as first:
        assert first.outbox.get(mine.id, lock=True).status == OutboxStatus.FAILED
        with pytest.raises(OperationalError, match="lock"), uow_factory() as second:
            second.session.execute(text("SET LOCAL lock_timeout = '100ms'"))
            second.outbox.get(mine.id, lock=True)
