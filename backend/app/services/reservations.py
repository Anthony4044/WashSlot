"""Use cases on the caller's reservations (SERVICE layer):
- list mine     GET /me/reservations           (US-4.3)
- fetch one     GET /reservations/{id}         (US-4.3)
- cancel        DELETE /reservations/{id}      (US-5.3)
- check in      POST /reservations/{id}/check-in (US-7.2)

Ownership is checked here: someone else's reservation is `not_found`, so we never reveal it exists.
"""
from app.domain.errors import DomainError
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import ReservationListDto, reservation_dto


class ReservationService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def list_mine(self, user_id: int) -> Outcome:
        """GET /me/reservations — the caller's bookings, newest first. Scope: reservations:read."""
        with self.uow_factory() as uow:
            now = uow.slots.now()
            items = []
            for reservation, details in uow.slots.list_for_user(user_id):
                reservation.expire_if_stale(now)  # lazy expiry, shown only: nothing is saved
                items.append(reservation_dto(reservation, details))
        return Outcome.success(ReservationListDto(reservations=items))

    def get(self, user_id: int, reservation_id: int) -> Outcome:
        """GET /reservations/{id}. Ownership lives here: someone else's -> not_found."""
        with self.uow_factory() as uow:
            slot = uow.slots.get_for_reservation(reservation_id)
            reservation = slot.reservation(reservation_id) if slot else None
            if reservation is None or reservation.user_id != user_id:
                return Outcome.failure("not_found")
            reservation.expire_if_stale(uow.slots.now())  # lazy expiry, shown only: nothing is saved
            details = uow.slots.details(slot.id)
        return Outcome.success(reservation_dto(reservation, details))

    def cancel(self, user_id: int, reservation_id: int) -> Outcome:
        """DELETE /reservations/{id}. Only before the slot starts; already cancelled → 204 again."""
        try:
            with self.uow_factory() as uow:
                slot = uow.slots.get_for_reservation(reservation_id, lock=True)
                reservation = slot.reservation(reservation_id) if slot else None
                if reservation is None or reservation.user_id != user_id:
                    return Outcome.failure("not_found")
                slot.cancel(reservation_id, uow.slots.now())
                uow.slots.save(slot)
        except DomainError as refused:
            return Outcome.failure(refused.code)
        return Outcome.success(None)

    def check_in(self, user_id: int, reservation_id: int, *, is_operator: bool = False) -> Outcome:
        """Record arrival for the customer who booked or the operator assigned to the laundromat."""
        try:
            with self.uow_factory() as uow:
                slot = uow.slots.get_for_reservation(reservation_id, lock=True)
                reservation = slot.reservation(reservation_id) if slot else None
                if reservation is None or (reservation.user_id != user_id and not is_operator):
                    return Outcome.failure("not_found")
                details = uow.slots.details(slot.id)
                if reservation.user_id != user_id:
                    laundromat = uow.laundromats.get(details.laundromat_id)
                    if laundromat is None or laundromat.operator_id != user_id:
                        return Outcome.failure("not_found")
                already_checked_in = reservation.checked_in_at is not None
                checked_in = slot.check_in(reservation_id, uow.slots.now())
                if not already_checked_in:
                    uow.slots.save(slot)
        except DomainError as refused:
            return Outcome.failure(refused.code)
        return Outcome.success(reservation_dto(checked_in, details))
