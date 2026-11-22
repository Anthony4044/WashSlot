"""Rule violations. Each carries a stable, machine-readable code.

The domain names WHAT went wrong; the interface layer (app/api/errors.py) decides the HTTP status.
Adding a code? Add it to the catalog in app/api/errors.py and to the contract's error catalog.
"""


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, code: str | None = None):
        if code is not None:
            self.code = code
        super().__init__(self.code)


class NotFound(DomainError):
    code = "not_found"


class SlotUnavailable(DomainError):
    code = "slot_unavailable"


class HoldExpired(DomainError):
    code = "hold_expired"


class AlreadyCancelled(DomainError):
    code = "already_cancelled"


class TooLateToCancel(DomainError):
    code = "too_late_to_cancel"


class ReservationNotConfirmed(DomainError):
    code = "reservation_not_confirmed"


class TooLateToCheckIn(DomainError):
    code = "too_late_to_check_in"
