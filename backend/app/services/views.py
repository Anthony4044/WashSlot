"""DTOs shaped like the contract schemas. Built once and reused by the use cases that return them."""
from datetime import date, datetime
from typing import Literal

from app.domain.enums import MachineType, OutboxStatus, ReservationStatus
from app.domain.laundromat import Laundromat
from app.domain.machine import Machine
from app.domain.notification import OutboxMessage
from app.domain.slot import Reservation, SlotDetails
from app.services.dto import Dto
from app.services.ids import HOLD, LAUNDROMAT, MACHINE, NOTIFICATION, RESERVATION, SLOT, format_id


class LaundromatDto(Dto):
    laundromat_id: str
    name: str
    address: str
    timezone: str


class LaundromatListDto(Dto):
    laundromats: list[LaundromatDto]


class TodayBookingDto(Dto):
    reservation_id: str
    machine_label: str
    start_time: datetime
    end_time: datetime
    customer_email: str
    status: Literal[ReservationStatus.CONFIRMED, ReservationStatus.NO_SHOW]
    checked_in_at: datetime | None


class TodayBookingsDto(Dto):
    date: date
    reservations: list[TodayBookingDto]


class SlotAvailabilityDto(Dto):
    slot_id: str
    start_time: datetime
    end_time: datetime
    status: str  # AVAILABLE | UNAVAILABLE


class MachineSlotsDto(Dto):
    machine_id: str
    label: str
    type: MachineType
    slots: list[SlotAvailabilityDto]


class MachineSlotsListDto(Dto):
    machines: list[MachineSlotsDto]


class HoldDto(Dto):
    hold_id: str
    slot_id: str
    status: ReservationStatus
    expires_at: datetime
    confirmation_email: str
    laundromat_id: str
    laundromat_name: str
    machine_id: str
    machine_label: str
    machine_type: MachineType
    start_time: datetime
    end_time: datetime


class ReservationDto(Dto):
    reservation_id: str
    slot_id: str
    status: ReservationStatus
    confirmation_email: str
    laundromat_id: str
    laundromat_name: str
    machine_id: str
    machine_label: str
    machine_type: MachineType
    start_time: datetime
    end_time: datetime
    created_at: datetime
    checked_in_at: datetime | None


class ReservationListDto(Dto):
    reservations: list[ReservationDto]


class MachineDto(Dto):
    machine_id: str
    label: str
    type: MachineType
    reservable: bool


class MachineListDto(Dto):
    machines: list[MachineDto]


class SlotsCreatedDto(Dto):
    created: int
    skipped: int  # already existed, or already started


class NotificationDto(Dto):
    notification_id: str
    reservation_id: str
    laundromat_id: str
    laundromat_name: str
    timezone: str
    recipient: str
    machine_label: str
    start_time: datetime
    end_time: datetime
    status: OutboxStatus
    attempts: int
    last_error: str | None
    next_attempt_at: datetime | None  # only while PENDING
    sent_at: datetime | None
    created_at: datetime


class NotificationListDto(Dto):
    notifications: list[NotificationDto]


def _where_and_when(details: SlotDetails) -> dict:
    return {
        "slot_id": format_id(SLOT, details.slot_id),
        "laundromat_id": format_id(LAUNDROMAT, details.laundromat_id),
        "laundromat_name": details.laundromat_name,
        "machine_id": format_id(MACHINE, details.machine_id),
        "machine_label": details.machine_label,
        "machine_type": details.machine_type,
        "start_time": details.start_time,
        "end_time": details.end_time,
    }


def hold_dto(r: Reservation, details: SlotDetails) -> HoldDto:
    return HoldDto(hold_id=format_id(HOLD, r.id), status=r.status, expires_at=r.expires_at,
                   confirmation_email=r.confirmation_email, **_where_and_when(details))


def reservation_dto(r: Reservation, details: SlotDetails) -> ReservationDto:
    return ReservationDto(reservation_id=format_id(RESERVATION, r.id), status=r.status,
                          confirmation_email=r.confirmation_email, created_at=r.created_at,
                          checked_in_at=r.checked_in_at, **_where_and_when(details))


def laundromat_dto(lm: Laundromat) -> LaundromatDto:
    return LaundromatDto(laundromat_id=format_id(LAUNDROMAT, lm.id), name=lm.name, address=lm.address,
                         timezone=lm.timezone)


def machine_dto(m: Machine) -> MachineDto:
    return MachineDto(machine_id=format_id(MACHINE, m.id), label=m.label, type=m.type, reservable=m.reservable)


def notification_dto(m: OutboxMessage, lm: Laundromat) -> NotificationDto:
    """Who and what the email is about comes from its payload: exactly what the customer gets."""
    return NotificationDto(
        notification_id=format_id(NOTIFICATION, m.id),
        reservation_id=format_id(RESERVATION, m.reservation_id),
        laundromat_id=format_id(LAUNDROMAT, lm.id),
        laundromat_name=lm.name,
        timezone=lm.timezone,
        recipient=m.payload["to"],
        machine_label=m.payload["machineLabel"],
        start_time=datetime.fromisoformat(m.payload["startTime"]),
        end_time=datetime.fromisoformat(m.payload["endTime"]),
        status=m.status,
        attempts=m.attempts,
        last_error=m.last_error,
        next_attempt_at=m.next_attempt_at if m.status == OutboxStatus.PENDING else None,
        sent_at=m.sent_at,
        created_at=m.created_at,
    )
