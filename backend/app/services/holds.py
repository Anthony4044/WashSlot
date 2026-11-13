"""Use cases on holds: look at my hold (GET /holds/{holdId}) and confirm it (POST /holds/{holdId}/confirm).

US-4.1 adds place_hold here. A hold and the reservation it becomes are the same row, so hold_7 and
res_7 name the same thing. Someone else's hold is `not_found`: we never reveal that it exists.
"""
from app.domain.errors import DomainError
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import hold_dto, reservation_dto


class HoldService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

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
