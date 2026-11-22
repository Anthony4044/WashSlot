"""The notification outbox (US-6.1): emails we still owe customers, kept in our own database.

Why an outbox? Confirming must never depend on the email service being up. So confirm only writes
a PENDING row, in the same transaction as the reservation (both are saved, or neither is). The
worker sends it later and, if the email service fails, tries again with growing waits.

This file holds the rules only: what a message contains and what happens after a failed try.
No HTTP and no SQL here.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.enums import OutboxStatus
from app.domain.slot import Reservation, SlotDetails

CONFIRMATION_EMAIL = "SEND_CONFIRMATION_EMAIL"

# Wait after the 1st, 2nd, ... 5th failed try. The 6th failure is final.
RETRY_DELAYS = [
    timedelta(seconds=30),
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=4),
    timedelta(minutes=8),
]
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1  # 6

# While the worker is sending, the message is pushed this far into the future, so another worker
# does not pick it up too. If the worker crashes mid-send, the message comes back after this time.
CLAIM_LEASE = timedelta(minutes=2)


@dataclass
class OutboxMessage:
    id: int | None  # None until the data layer saves it
    reservation_id: int
    laundromat_id: int
    type: str
    payload: dict  # everything needed to write the email, so sending needs no other lookup
    next_attempt_at: datetime  # do not send before this time
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0  # how many sends were tried
    last_error: str | None = None
    correlation_id: str | None = None  # filled in by US-8.2 (tracing)
    sent_at: datetime | None = None
    created_at: datetime | None = None

    def mark_sent(self, now: datetime) -> None:
        self.attempts += 1
        self.status = OutboxStatus.SENT
        self.sent_at = now
        self.last_error = None

    def mark_failed_try(self, error: str, retryable: bool, now: datetime) -> None:
        """One send failed. Either schedule the next try, or give up (FAILED).

        retryable=True  : network error or a 5xx from the email service -> wait, then try again
        retryable=False : the email service refused the email itself (a 4xx) -> retrying won't help
        """
        self.attempts += 1
        self.last_error = error[:500]  # keep the column small
        if not retryable or self.attempts >= MAX_ATTEMPTS:
            self.status = OutboxStatus.FAILED
            return
        self.next_attempt_at = now + RETRY_DELAYS[self.attempts - 1]

    def retry(self, now: datetime) -> bool:
        """An operator asks to send a FAILED email again (US-7.3): a fresh start, due now.

        attempts goes back to 0, so it gets MAX_ATTEMPTS new tries with the same backoff as the first
        time. last_error stays until the next try replaces it, so the operator still sees why it failed.
        Anything not FAILED is left alone (idempotent): PENDING is already on its way, SENT already
        arrived, and sending it again would email the customer twice. Returns True if it changed.
        """
        if self.status != OutboxStatus.FAILED:
            return False
        self.status = OutboxStatus.PENDING
        self.attempts = 0
        self.next_attempt_at = now
        return True


def confirmation_email(reservation: Reservation, details: SlotDetails, laundromat_address: str,
                       timezone: str, now: datetime) -> OutboxMessage:
    """The message written when a hold is confirmed: who to email, and where and when the booking is."""
    return OutboxMessage(
        id=None,
        reservation_id=reservation.id,
        laundromat_id=details.laundromat_id,
        type=CONFIRMATION_EMAIL,
        next_attempt_at=now,  # send as soon as possible
        payload={
            "to": reservation.confirmation_email,
            "laundromatName": details.laundromat_name,
            "laundromatAddress": laundromat_address,
            "machineLabel": details.machine_label,
            "machineType": details.machine_type.value,
            "startTime": details.start_time.isoformat(),
            "endTime": details.end_time.isoformat(),
            "timezone": timezone,  # the laundromat's, so the email shows local time
        },
    )
