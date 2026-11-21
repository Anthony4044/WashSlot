import enum


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    OPERATOR = "OPERATOR"


class MachineType(str, enum.Enum):
    WASHER = "WASHER"
    DRYER = "DRYER"


class ReservationStatus(str, enum.Enum):
    HELD = "HELD"  # 10-minute hold while the customer confirms
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"  # hold not confirmed in time
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"  # not checked in 15 min after start


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"  # waiting to be sent (or to be retried at next_attempt_at)
    SENT = "SENT"
    FAILED = "FAILED"  # gave up: too many tries, or the email service refused it for good
