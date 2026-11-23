"""Public identifiers: prefix + opaque number, e.g. slot_1842.

The database keeps plain integer keys; the prefix exists only at the boundary. Ids promise
nothing but uniqueness - never encode dates, names or positions in them.
"""
import re

from app.domain.errors import NotFound

LAUNDROMAT = "lm"
MACHINE = "mch"
SLOT = "slot"
HOLD = "hold"
RESERVATION = "res"
USER = "usr"
NOTIFICATION = "ntf"

_PATTERN = re.compile(r"^([a-z]+)_([1-9][0-9]{0,18})$")


def format_id(prefix: str, number: int) -> str:
    return f"{prefix}_{number}"


def parse_id(prefix: str, public_id: str) -> int:
    """'slot_1842' -> 1842. A malformed or wrong-prefix id names nothing, so it is not_found."""
    match = _PATTERN.match(public_id or "")
    if not match or match.group(1) != prefix:
        raise NotFound()
    return int(match.group(2))


def id_pattern(prefix: str) -> str:
    """The JSON Schema / OpenAPI pattern for this prefix, e.g. ^slot_[1-9][0-9]*$."""
    return f"^{prefix}_[1-9][0-9]*$"
