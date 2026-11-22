"""Use cases on holds (the SERVICE layer):
- place a hold      POST /slots/{slotId}/holds      (US-4.1, safe retries US-5.2)
- look at my hold   GET /holds/{holdId}             (US-4.2)
- confirm it        POST /holds/{holdId}/confirm    (US-4.2)

A hold and the reservation it becomes are the same row, so hold_7 and res_7 name the same thing.
Someone else's hold is `not_found`: we never reveal that it exists.
"""
from app.domain.enums import ReservationStatus
from app.domain.errors import DomainError
from app.domain.notification import confirmation_email
from app.services.idempotency import Attempt, run_once
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.services.views import HoldDto, hold_dto, reservation_dto

DEFAULT_HOLD_MINUTES = 10  # the proposal's 10 minutes; the app passes HOLD_MINUTES from settings
PLACE_HOLD = "placeHold"  # the endpoint name stored with each idempotency record (the contract's operationId)


class HoldService:
    def __init__(self, uow_factory: UnitOfWorkFactory, hold_minutes: int = DEFAULT_HOLD_MINUTES):
        self.uow_factory = uow_factory  # makes one unit of work (= one database transaction) per use case
        self.hold_minutes = hold_minutes

    def place_hold(self, user_id: int, slot_id: int, confirmation_email: str, idempotency_key: str) -> Outcome:
        """Use case: hold a slot for 10 minutes. Success -> HoldDto; else "not_found" or "slot_unavailable".

        Pessimistic locking: read, decide and write in ONE transaction, with the slot
        row locked from the read until the commit:

            BEGIN
            SELECT ... FROM machine_slots WHERE id = 5 FOR UPDATE   -- read AND lock; a rival waits here
            (Python) the domain rule decides, using the database clock
            UPDATE stale holds to EXPIRED, INSERT the new HELD row
            INSERT the idempotency record (US-5.2)
            COMMIT                                                   -- lock released; the rival wakes up

        So when two customers click at the same moment, they are served one after the other. The first
        gets the hold. The second wakes up, sees the first one's hold, and gets slot_unavailable.

        US-5.2: the same key and the same request again (a retry after a lost response) gets the
        first attempt's outcome back, replayed, and never a second hold. The same key for another
        slot or another email is "idempotency_key_reuse". See app/services/idempotency.py.
        """
        attempt = Attempt.of(user_id, idempotency_key, PLACE_HOLD,
                             slot_id=slot_id, confirmation_email=confirmation_email)
        return run_once(self.uow_factory, attempt, HoldDto,
                        lambda uow: self._place_hold(uow, user_id, slot_id, confirmation_email))

    def _place_hold(self, uow: UnitOfWork, user_id: int, slot_id: int, confirmation_email: str) -> Outcome:
        """The hold itself, inside run_once's unit of work. A refusal is RETURNED, so it is stored too."""
        # 1. Load the whole aggregate (the slot and its reservations) and LOCK its root row.
        slot = uow.slots.get(slot_id, lock=True)
        if slot is None:
            return Outcome.failure("not_found")

        # 2. The domain rule decides. If the slot is taken it raises SlotUnavailable. Nothing has been
        #    written yet (only save() writes), so the refusal can be stored and committed on its own.
        try:
            hold = slot.place_hold(user_id, confirmation_email, uow.slots.now(), self.hold_minutes)
        except DomainError as refused:
            return Outcome.failure(refused.code)  # "slot_unavailable"; the interface layer makes it a 409

        # 3. Write it back: the repository INSERTs the new hold (and UPDATEs any it expired).
        uow.slots.save(slot)
        details = uow.slots.details(slot.id)  # where and when, for the response
        # Not real until run_once's unit of work COMMITs, which happens before anyone sees this
        # outcome (never say "success" before COMMIT returns).
        return Outcome.success(hold_dto(hold, details))

    def get_hold(self, user_id: int, hold_id: int) -> Outcome:
        """The caller's hold, with its status as of now (a hold past its expiry shows EXPIRED)."""
        with self.uow_factory() as uow:
            slot = uow.slots.get_for_reservation(hold_id)
            hold = slot.reservation(hold_id) if slot else None
            if hold is None or hold.user_id != user_id:
                return Outcome.failure("not_found")
            slot.expire_stale_holds(uow.slots.now())  # same rule as everywhere; nothing is saved
            details = uow.slots.details(slot.id)
        return Outcome.success(hold_dto(hold, details))

    def confirm(self, user_id: int, hold_id: int) -> Outcome:
        """HELD and live -> CONFIRMED. Already confirmed -> the same reservation (naturally idempotent).

        One unit of work: lock the slot (the aggregate root, never just the reservation row), check
        the owner, let the domain rule decide with the database clock, save.

        US-6.1: the first confirm also writes a confirmation email to the outbox, in this SAME unit
        of work, so the reservation and its email are saved together or not at all. Resend is
        never called here; the worker sends the email after we commit.
        """
        try:
            with self.uow_factory() as uow:
                slot = uow.slots.get_for_reservation(hold_id, lock=True)
                hold = slot.reservation(hold_id) if slot else None
                if hold is None or hold.user_id != user_id:
                    return Outcome.failure("not_found")
                first_confirm = hold.status == ReservationStatus.HELD  # a repeat must not send a 2nd email
                now = uow.slots.now()
                reservation = slot.confirm(hold_id, now)
                uow.slots.save(slot)
                details = uow.slots.details(slot.id)
                if first_confirm:
                    laundromat = uow.laundromats.get(details.laundromat_id)
                    uow.outbox.add(confirmation_email(
                        reservation, details,
                        laundromat_address=laundromat.address if laundromat else "",
                        timezone=laundromat.timezone if laundromat else "UTC",
                        now=now,
                    ))
        except DomainError as refused:  # raised inside the unit of work, so nothing was written
            return Outcome.failure(refused.code)
        return Outcome.success(reservation_dto(reservation, details))

    def expire_stale_holds(self) -> int:
        """Worker job (US-5.1): mark every hold whose time ran out as EXPIRED. Returns how many.

        Not needed for correctness: every request already treats a stale hold as expired (lazy
        expiry). This job only makes the database say so too, so it is tidy for reports.
        """
        with self.uow_factory() as uow:
            return uow.slots.expire_all_stale_holds()
