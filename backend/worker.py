"""The background worker: a separate process that runs small jobs on a timer.

Run it next to the API, from the backend folder:

    python worker.py

How it works: a loop that wakes up every second and runs each job whose turn has come.
Each job is a plain function that gets a unit-of-work factory (the same one the API uses),
so it talks to the database through the service layer, never with its own SQL.

Adding a job (US-5.2 retention, US-7.2 no-shows, ...): write a function below that takes
`uow_factory`, then add ONE line to JOBS. Keep both sides when you resolve a merge conflict here.

Requests still enforce hold expiry and the check-in deadline when the worker is stopped.
The worker persists no-shows so attendants can release the machines to walk-ins.
"""
import logging
import time

from app.core.config import get_settings
from app.core.email import get_email_sender
from app.core.logging import configure_logging
from app.data.database import get_session_factory
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.services.emails import EmailService
from app.services.holds import HoldService
from app.services.idempotency import delete_old_records
from app.services.reservations import ReservationService
from app.services.slot_generation import maintain_slot_window
from app.services.unit_of_work import UnitOfWorkFactory

log = logging.getLogger("worker")


# --- The jobs -------------------------------------------------------------------------------

def generate_slots(uow_factory: UnitOfWorkFactory) -> None:
    count = maintain_slot_window(uow_factory)
    if count:
        log.info("created %d upcoming slot(s)", count)


def expire_holds(uow_factory: UnitOfWorkFactory) -> None:
    """US-5.1: holds nobody confirmed in 10 minutes become EXPIRED."""
    count = HoldService(uow_factory).expire_stale_holds()
    if count:
        log.info("expired %d hold(s)", count)


def send_emails(uow_factory: UnitOfWorkFactory) -> None:
    """US-6.1: send the confirmation emails waiting in the outbox (failed ones are retried later)."""
    count = EmailService(uow_factory, get_email_sender()).send_due_emails()
    if count:
        log.info("sent %d email(s)", count)


def mark_no_shows(uow_factory: UnitOfWorkFactory) -> None:
    """US-7.2: unchecked confirmed bookings become NO_SHOW after the 15-minute grace period."""
    count = ReservationService(uow_factory).mark_no_shows()
    if count:
        log.info("marked %d no-show(s)", count)


def forget_old_idempotency_keys(uow_factory: UnitOfWorkFactory) -> None:
    """US-5.2: delete Idempotency-Key records older than IDEMPOTENCY_RETENTION_HOURS (at least 24)."""
    count = delete_old_records(uow_factory, get_settings().idempotency_retention_hours)
    if count:
        log.info("forgot %d idempotency key(s)", count)


# (name, function, run every N seconds). Add one line per job.
JOBS = [
    ("generate upcoming slots", generate_slots, 3600),
    ("expire holds", expire_holds, 30),
    ("mark no-shows", mark_no_shows, 30),
    ("send emails", send_emails, 5),
    ("forget old idempotency keys", forget_old_idempotency_keys, 600),
]


# --- The loop -------------------------------------------------------------------------------

def run_due_jobs(uow_factory: UnitOfWorkFactory, next_run: dict[str, float], now: float) -> None:
    """Run every job whose time has come, then book its next run.

    A job that fails is logged and tried again on its next turn: one bad job never stops the others.
    """
    for name, job, every_seconds in JOBS:
        if now < next_run.get(name, 0):
            continue  # not its turn yet
        next_run[name] = now + every_seconds
        try:
            job(uow_factory)
        except Exception:
            log.exception("job %r failed; it will run again in %d s", name, every_seconds)


def main() -> None:
    configure_logging()
    session_factory = get_session_factory()  # DATABASE_URL from backend/.env

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    log.info("worker started with jobs: %s", ", ".join(name for name, _, _ in JOBS))
    next_run: dict[str, float] = {}  # job name -> when it runs next (empty: everything runs now)
    while True:
        run_due_jobs(uow_factory, next_run, time.monotonic())
        time.sleep(1)


if __name__ == "__main__":
    main()
