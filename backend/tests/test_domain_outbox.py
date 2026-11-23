"""The outbox rules on their own (US-8.4): no worker, no database, no HTTP.

tests/test_emails.py runs these rules through EmailService. Here we check the rules themselves:
- confirming writes one PENDING email, due now, that carries everything needed to send it
- a failed try waits 30 s, 1 min, 2 min, 4 min, then 8 min; the 6th failure is final
- a refused email (a 4xx) is FAILED at once: trying again won't help
- a sent email is SENT, with no error left on it
"""
from datetime import UTC, datetime

import pytest

from app.domain.enums import MachineType, OutboxStatus, ReservationStatus
from app.domain.notification import (
    CONFIRMATION_EMAIL,
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    OutboxMessage,
    confirmation_email,
)
from app.domain.slot import Reservation, SlotDetails

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)
START = datetime(2030, 1, 8, 14, 0, tzinfo=UTC)


def booking() -> tuple[Reservation, SlotDetails]:
    reservation = Reservation(id=70, slot_id=5, user_id=1, status=ReservationStatus.CONFIRMED,
                              confirmation_email="kim@example.com", confirmed_at=NOW)
    details = SlotDetails(slot_id=5, laundromat_id=3, laundromat_name="Spin City", machine_id=12,
                          machine_label="Washer 4", machine_type=MachineType.WASHER,
                          start_time=START, end_time=START.replace(hour=15))
    return reservation, details


def new_email() -> OutboxMessage:
    reservation, details = booking()
    return confirmation_email(reservation, details, "1 Main St", "America/Toronto", NOW, "booking-demo")


# --- writing the email -----------------------------------------------------------------------------

def test_a_confirmation_is_one_pending_email_due_now():
    email = new_email()

    assert (email.id, email.type, email.status, email.attempts) == (None, CONFIRMATION_EMAIL, OutboxStatus.PENDING, 0)
    assert email.next_attempt_at == NOW  # the worker may send it straight away
    assert (email.reservation_id, email.laundromat_id) == (70, 3)
    assert email.correlation_id == "booking-demo"  # the confirm request's id, kept for the worker's logs


def test_the_email_carries_everything_needed_to_send_it():
    assert new_email().payload == {
        "to": "kim@example.com", "laundromatName": "Spin City", "laundromatAddress": "1 Main St",
        "machineLabel": "Washer 4", "machineType": "WASHER", "startTime": "2030-01-08T14:00:00+00:00",
        "endTime": "2030-01-08T15:00:00+00:00", "timezone": "America/Toronto",
    }  # so sending needs no other lookup, even if the slot changes later


# --- failed tries --------------------------------------------------------------------------------------

def test_each_failed_try_waits_longer_and_the_sixth_is_final():
    email = new_email()

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        email.mark_failed_try("Resend answered 503", retryable=True, now=NOW)
        assert (email.status, email.attempts) == (OutboxStatus.PENDING, attempt)
        assert email.next_attempt_at == NOW + delay  # 30 s, 1 min, 2 min, 4 min, 8 min

    email.mark_failed_try("Resend answered 503", retryable=True, now=NOW)

    assert (email.status, email.attempts) == (OutboxStatus.FAILED, MAX_ATTEMPTS)
    assert email.last_error == "Resend answered 503"


def test_a_refused_email_is_failed_at_once():
    email = new_email()

    email.mark_failed_try("Resend answered 422: invalid recipient", retryable=False, now=NOW)

    assert (email.status, email.attempts) == (OutboxStatus.FAILED, 1)
    assert email.next_attempt_at == NOW  # no next try is scheduled


def test_a_long_error_is_cut_to_500_characters():
    email = new_email()

    email.mark_failed_try("x" * 2000, retryable=True, now=NOW)

    assert len(email.last_error) == 500


# --- sent ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("failures_first", [0, 2])
def test_a_sent_email_is_sent_and_keeps_no_error(failures_first):
    email = new_email()
    for _ in range(failures_first):
        email.mark_failed_try("timeout", retryable=True, now=NOW)

    email.mark_sent(NOW)

    assert (email.status, email.sent_at, email.last_error) == (OutboxStatus.SENT, NOW, None)
    assert email.attempts == failures_first + 1  # the successful try counts too
