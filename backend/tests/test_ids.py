import re

import pytest

from app.domain.errors import NotFound
from app.services.ids import HOLD, SLOT, format_id, id_pattern, parse_id


def test_round_trip():
    assert format_id(SLOT, 1842) == "slot_1842"
    assert parse_id(SLOT, "slot_1842") == 1842


@pytest.mark.parametrize("bad", ["hold_1842", "slot_", "slot_0", "slot_01", "slot_abc", "1842", "", "slot_1842x"])
def test_malformed_or_wrong_prefix_is_not_found(bad):
    with pytest.raises(NotFound):
        parse_id(SLOT, bad)


def test_pattern_matches_formatted_ids():
    assert re.match(id_pattern(HOLD), format_id(HOLD, 7))
    assert not re.match(id_pattern(HOLD), "slot_7")
