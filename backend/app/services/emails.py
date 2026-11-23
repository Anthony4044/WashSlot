"""Sending the emails waiting in the outbox (US-6.1). Run by the worker, never by a request.

For each message that is due, three short steps:

    1. claim it        (one small transaction: lock the row, push it into the future, commit)
    2. send it         (NO transaction open: the email service may be slow or down)
    3. record result   (one small transaction: SENT, or a failed try with its next retry time)

So a slow email service never holds a database lock, and a reservation is never undone because
an email failed: the reservation was committed earlier, on its own, by confirm.
"""
import logging
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.email import EmailSendError
from app.core.logging import correlation_context
from app.domain.enums import OutboxStatus
from app.domain.notification import OutboxMessage
from app.services.unit_of_work import UnitOfWorkFactory

log = logging.getLogger(__name__)


class EmailSender(Protocol):
    """What we need from an email client (app/core/email.py, or a fake one in tests)."""

    def send(self, to: str, subject: str, text: str, idempotency_key: str) -> None: ...


class EmailService:
    def __init__(self, uow_factory: UnitOfWorkFactory, sender: EmailSender):
        self.uow_factory = uow_factory
        self.sender = sender

    def send_due_emails(self, limit: int = 20) -> int:
        """Send up to `limit` due messages. Returns how many were sent."""
        sent = 0
        for _ in range(limit):
            # 1. Claim the next due message.
            with self.uow_factory() as uow:
                message = uow.outbox.claim_next()
                if message is not None and message.correlation_id is None:
                    # Older rows and messages created outside HTTP still get a stable trace.
                    message.correlation_id = f"outbox-{message.id}"
                    uow.outbox.save(message)
            if message is None:
                break  # nothing more is due

            with correlation_context(message.correlation_id):
                try:
                    sent += self._send_message(message)
                except Exception:
                    log.exception("email delivery failed", extra={
                        "outboxId": message.id, "reservationId": message.reservation_id,
                    })
                    raise
        return sent

    def _send_message(self, message: OutboxMessage) -> int:
        details = {
            "outboxId": message.id, "reservationId": message.reservation_id, "attempt": message.attempts + 1,
        }
        log.info("sending confirmation email", extra=details)
        # 2. Send it, with no transaction open.
        subject, text = confirmation_text(message.payload)
        try:
            self.sender.send(message.payload["to"], subject, text, idempotency_key=f"outbox-{message.id}")
            error = None
        except EmailSendError as failed:
            error = failed

        # 3. Record what happened, using the database clock.
        with self.uow_factory() as uow:
            now = uow.slots.now()
            if error is None:
                message.mark_sent(now)
            else:
                message.mark_failed_try(str(error), error.retryable, now)
            uow.outbox.save(message)
        # Report the result only after its transaction commits.
        if error is None:
            log.info("confirmation email sent", extra=details)
            return 1
        if message.status == OutboxStatus.FAILED:
            log.warning("email %s FAILED after %d tries: %s", message.id, message.attempts, error, extra=details)
        else:
            log.warning("email %s try %d failed (%s); next try at %s",
                        message.id, message.attempts, error, message.next_attempt_at, extra=details)
        return 0


def confirmation_text(payload: dict) -> tuple[str, str]:
    """The confirmation email's subject and plain-text body, in the laundromat's local time."""
    timezone = ZoneInfo(payload["timezone"])
    start = datetime.fromisoformat(payload["startTime"]).astimezone(timezone)
    end = datetime.fromisoformat(payload["endTime"]).astimezone(timezone)
    day = f"{start:%A, %B} {start.day}"  # e.g. "Friday, November 27"
    hours = f"{start:%H:%M} to {end:%H:%M}"  # e.g. "18:00 to 19:00"
    machine = f"{payload['machineLabel']} ({payload['machineType'].lower()})"

    subject = f"WashSlot: {payload['machineLabel']} is yours on {day} at {start:%H:%M}"
    text = (
        "Your reservation is confirmed.\n"
        "\n"
        f"Laundromat: {payload['laundromatName']}, {payload['laundromatAddress']}\n"
        f"Machine:    {machine}\n"
        f"When:       {day}, {hours}\n"
        "\n"
        "Please check in within 15 minutes of the start time, or the machine goes to walk-in customers.\n"
        "Plans changed? You can cancel from My reservations any time before the start.\n"
    )
    return subject, text
