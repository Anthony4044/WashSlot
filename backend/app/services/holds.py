"""Use cases on holds (the SERVICE layer, lecture Ch. 5):
- place a hold      POST /slots/{slotId}/holds      (US-4.1)
- look at my hold   GET /holds/{holdId}             (US-4.2)
- confirm it        POST /holds/{holdId}/confirm    (US-4.2)

A hold and the reservation it becomes are the same row, so hold_7 and res_7 name the same thing.
Someone else's hold is `not_found`: we never reveal that it exists.
"""
from app.domain.errors import DomainError
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import hold_dto, reservation_dto

DEFAULT_HOLD_MINUTES = 10  # the proposal's 10 minutes; the app passes HOLD_MINUTES from settings


class HoldService:
    def __init__(self, uow_factory: UnitOfWorkFactory, hold_minutes: int = DEFAULT_HOLD_MINUTES):
        self.uow_factory = uow_factory  # makes one unit of work (= one database transaction) per use case
        self.hold_minutes = hold_minutes

    def place_hold(self, user_id: int, slot_id: int, confirmation_email: str) -> Outcome:
        """Use case: hold a slot for 10 minutes. Success -> HoldDto; else "not_found" or "slot_unavailable".

        Pessimistic locking (lecture Ch. 7): read, decide and write in ONE transaction, with the slot
        row locked from the read until the commit:

            BEGIN
            SELECT ... FROM machine_slots WHERE id = 5 FOR UPDATE   -- read AND lock; a rival waits here
            (Python) the domain rule decides, using the database clock
            UPDATE stale holds to EXPIRED, INSERT the new HELD row
            COMMIT                                                   -- lock released; the rival wakes up

        So when two customers click at the same moment, they are served one after the other. The first
        gets the hold. The second wakes up, sees the first one's hold, and gets slot_unavailable.
        """
        try:
            with self.uow_factory() as uow:  # BEGIN (one transaction)
                # 1. Load the whole aggregate (the slot and its reservations) and LOCK its root row.
                slot = uow.slots.get(slot_id, lock=True)
                if slot is None:
                    return Outcome.failure("not_found")

                # 2. The domain rule decides. If the slot is taken it raises SlotUnavailable, which
                #    leaves this block with an exception, so the unit of work rolls back.
                hold = slot.place_hold(user_id, confirmation_email, uow.slots.now(), self.hold_minutes)

                # 3. Write it back: the repository INSERTs the new hold (and UPDATEs any it expired).
                uow.slots.save(slot)
                details = uow.slots.details(slot.id)  # where and when, for the response
            # The block ended normally: COMMIT, and the lock is released. Only now is the hold real,
            # so only now do we report success (Ch. 7: say "success" only after COMMIT returns).
        except DomainError as refused:
            return Outcome.failure(refused.code)  # "slot_unavailable"; the interface layer makes it a 409
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
        """
        try:
            with self.uow_factory() as uow:
                slot = uow.slots.get_for_reservation(hold_id, lock=True)
                hold = slot.reservation(hold_id) if slot else None
                if hold is None or hold.user_id != user_id:
                    return Outcome.failure("not_found")
                reservation = slot.confirm(hold_id, uow.slots.now())
                uow.slots.save(slot)
                details = uow.slots.details(slot.id)
        except DomainError as refused:  # raised inside the unit of work, so nothing was written
            return Outcome.failure(refused.code)
        return Outcome.success(reservation_dto(reservation, details))
