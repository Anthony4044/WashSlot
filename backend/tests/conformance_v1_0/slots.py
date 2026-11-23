"""Find a slot through the API itself, as any outside client would (shared by the hold conformance tests)."""
from datetime import date, timedelta

import pytest


def find_free_slot(api) -> str:
    """The id of some AVAILABLE slot in the next 7 days, found by browsing like a customer would.

    Needs browsing (US-3.1) and seeded laundromats. Until both exist, the calling test is skipped
    and says why.
    """
    listing = api.get("/laundromats")
    if listing.status_code == 404:
        pytest.skip("GET /laundromats is not there yet (US-3.1)")
    for laundromat in listing.json()["laundromats"]:
        for days in range(1, 8):
            day = (date.today() + timedelta(days=days)).isoformat()
            grid = api.get(f"/laundromats/{laundromat['laundromatId']}/slots", params={"date": day}).json()
            for machine in grid["machines"]:
                for slot in machine["slots"]:
                    if slot["status"] == "AVAILABLE":
                        return slot["slotId"]
    pytest.skip("no free slot in the next 7 days: run the seed scripts")
