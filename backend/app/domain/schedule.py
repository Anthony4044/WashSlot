"""Which slots an operator's "Create slots" form asks for (US-7.1). Pure rules: no HTTP, no SQL.

Times are wall-clock times in the laundromat's own time zone ("08:00 in Montreal"), turned into
UTC instants here, day by day, so a slot starts at 08:00 local time on both sides of a DST change.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.errors import InvalidSchedule

MAX_DAYS = 31  # one request covers at most a month: keeps a single insert small
SLOT_LENGTHS = (30, 60, 90)  # minutes
END_OF_DAY = 24 * 60  # "24:00", midnight at the end of the day


def parse_local_time(text: str) -> int:
    """'08:30' -> 510 minutes after midnight. '24:00' is allowed (end of the day)."""
    hours, minutes = text.split(":")
    value = int(hours) * 60 + int(minutes)
    if not 0 <= value <= END_OF_DAY or int(minutes) >= 60:
        raise InvalidSchedule()
    return value


@dataclass(frozen=True)
class SlotSchedule:
    from_date: date
    to_date: date  # included
    open_minute: int  # minutes after local midnight
    close_minute: int
    slot_minutes: int

    def __post_init__(self):
        """The form's rules, checked once, wherever a schedule is made."""
        if self.slot_minutes not in SLOT_LENGTHS:
            raise InvalidSchedule()
        if self.to_date < self.from_date or (self.to_date - self.from_date).days >= MAX_DAYS:
            raise InvalidSchedule()
        if not 0 <= self.open_minute < self.close_minute <= END_OF_DAY:
            raise InvalidSchedule()
        if self.close_minute - self.open_minute < self.slot_minutes:
            raise InvalidSchedule()  # not even one slot fits

    @classmethod
    def of(cls, from_date: date, to_date: date, open_time: str, close_time: str, slot_minutes: int) -> "SlotSchedule":
        return cls(from_date, to_date, parse_local_time(open_time), parse_local_time(close_time), slot_minutes)

    def days(self) -> list[date]:
        return [self.from_date + timedelta(days=i) for i in range((self.to_date - self.from_date).days + 1)]

    def slot_times(self, timezone: str) -> list[tuple[datetime, datetime]]:
        """Every (start, end) the schedule asks for, as UTC instants, earliest first.

        Back to back from openTime; the last slot ends at or before closeTime.
        """
        tz = ZoneInfo(timezone)
        times = []
        for day in self.days():
            start = self.open_minute
            while start + self.slot_minutes <= self.close_minute:
                times.append((_instant(day, start, tz), _instant(day, start + self.slot_minutes, tz)))
                start += self.slot_minutes
        return times


def _instant(day: date, minute: int, tz: ZoneInfo) -> datetime:
    """`minute` minutes after midnight on `day`, read on the laundromat's wall clock, as a UTC instant."""
    wall = datetime.combine(day, time(0)) + timedelta(minutes=minute)  # naive local time ("24:00" = next day)
    return wall.replace(tzinfo=tz).astimezone(UTC)
