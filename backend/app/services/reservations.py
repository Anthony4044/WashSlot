"""Use cases on the caller's reservations (SERVICE layer):
- list mine     GET /me/reservations           (US-4.3)
- fetch one     GET /reservations/{id}         (US-4.3)

Ownership is checked here: someone else's reservation is `not_found`, so we never reveal it exists.
"""
from app.domain.enums import ReservationStatus
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
                # Same lazy expiry as get_hold: a HELD past expires_at shows EXPIRED (nothing saved).
                if (
                    reservation.status == ReservationStatus.HELD
                    and reservation.expires_at is not None
                    and reservation.expires_at <= now
                ):
                    reservation.status = ReservationStatus.EXPIRED
                items.append(reservation_dto(reservation, details))
        return Outcome.success(ReservationListDto(reservations=items))
