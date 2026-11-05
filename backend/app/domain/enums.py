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
