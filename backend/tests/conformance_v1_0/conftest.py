"""Conformance tests run against a live server named by CONFORMANCE_BASE_URL.

    uvicorn app.main:app                                   # terminal 1
    CONFORMANCE_BASE_URL=http://localhost:8000 pytest tests/conformance   # terminal 2

Without CONFORMANCE_BASE_URL every test here is skipped (that is what plain `pytest` does in CI).
The tests talk HTTP only. They create their own users through the API, so any database works,
but they do leave those users behind: never point them at the demo database.
"""
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.conformance_v1_0.users import PASSWORD, unique_email

HERE = Path(__file__).resolve().parent
BASE_URL = os.environ.get("CONFORMANCE_BASE_URL", "").rstrip("/")


def pytest_collection_modifyitems(items):
    if BASE_URL:
        return
    skip = pytest.mark.skip(reason="CONFORMANCE_BASE_URL is not set")
    for item in items:  # this hook sees every collected test, so only skip the ones in this folder
        if HERE in item.path.parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        yield client


@pytest.fixture
def customer(api) -> dict[str, str]:
    """A fresh customer, registered and logged in through the API: {"email", "Authorization"}.

    Use it as headers: api.get("/me/reservations", headers={"Authorization": customer["Authorization"]}).
    """
    email = unique_email()
    assert api.post("/auth/register", json={"email": email, "password": PASSWORD}).status_code == 201
    token = api.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["accessToken"]
    return {"email": email, "Authorization": f"Bearer {token}"}
