"""Restart persistence check (US-8.4): a booking survives deleting and recreating every container.

    python scripts/restart_check.py               # from the repository root, with Docker running
    python scripts/restart_check.py api worker    # only these services (CI skips the front end)

1. Start the stack (docker compose up -d --build) and wait until /health/ready says the database is up.
2. Register a new customer, find a free slot by browsing, hold it and confirm it: a reservation.
3. docker compose down, then up again. Every container is deleted and a new one is created, so
   anything kept only in a container (its memory or its files) is gone. Volumes are kept: that is
   where Docker keeps data on purpose (the JWT signing keys, and Postgres's files in CI).
4. Using the token from step 2, read the reservation back. It must be there, unchanged. Logging
   in again must work too. Then cancel the reservation, so the slot is free again.

Which database? The one compose uses. By default that is DATABASE_URL in backend/.env (Neon), so
each run leaves a restart-check-...@example.com customer and a cancelled booking there. CI adds
compose.ci.yaml (COMPOSE_FILE=compose.yaml:compose.ci.yaml), which runs Postgres in a container
with a named volume, so there the database's own container restarts too.

Exits 0 when the booking survived, 1 otherwise. Uses only the standard library.
"""
import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import date, timedelta
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "restart-check-pass-1"
READY_TIMEOUT_S = 180


class CheckFailed(Exception):
    pass


def compose(*args: str) -> None:
    print(f"   $ docker compose {' '.join(args)}", flush=True)
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True)


def container_ids() -> set[str]:
    out = subprocess.run(["docker", "compose", "ps", "--all", "--quiet"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return set(out.split())


class Api:
    """A tiny JSON client. Every request carries one X-Correlation-ID, so the logs show this run."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.correlation_id = f"restart-check-{uuid.uuid4().hex[:8]}"

    def call(self, method: str, path: str, body: dict | None = None, token: str | None = None,
             headers: dict[str, str] | None = None) -> tuple[int, dict | None]:
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base_url + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("X-Correlation-ID", self.correlation_id)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urlopen(request, timeout=15) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        return status, (json.loads(raw) if raw else None)

    def expect(self, status: int, method: str, path: str, **kwargs) -> dict | None:
        got, body = self.call(method, path, **kwargs)
        if got != status:
            raise CheckFailed(f"{method} {path}: expected {status}, got {got} {body}")
        return body

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                if self.call("GET", "/health/ready")[0] == 200:
                    return
            except (OSError, HTTPException):  # not listening yet, or reset while starting
                pass
            time.sleep(2)
        raise CheckFailed(f"the API was not ready after {READY_TIMEOUT_S} s: see docker compose logs migrate api")


def find_free_slot(api: Api) -> str:
    """Some AVAILABLE slot in the next 7 days, found by browsing as a customer would."""
    for laundromat in api.expect(200, "GET", "/laundromats")["laundromats"]:
        for days in range(1, 8):
            day = (date.today() + timedelta(days=days)).isoformat()
            grid = api.expect(200, "GET", f"/laundromats/{laundromat['laundromatId']}/slots?date={day}")
            for machine in grid["machines"]:
                for slot in machine["slots"]:
                    if slot["status"] == "AVAILABLE":
                        return slot["slotId"]
    raise CheckFailed("no free slot in the next 7 days: run the seed scripts (backend/README.md)")


def run(api: Api, services: list[str]) -> None:
    print("1. Start the stack", flush=True)
    compose("up", "--detach", "--build", *services)
    api.wait_until_ready()

    print("2. Book a slot", flush=True)
    email = f"restart-check-{uuid.uuid4().hex[:10]}@example.com"
    login = {"email": email, "password": PASSWORD}
    api.expect(201, "POST", "/auth/register", body=login)
    token = api.expect(200, "POST", "/auth/login", body=login)["accessToken"]
    slot_id = find_free_slot(api)
    hold = api.expect(201, "POST", f"/slots/{slot_id}/holds", body={"confirmationEmail": email}, token=token,
                      headers={"Idempotency-Key": str(uuid.uuid4())})
    booked = api.expect(200, "POST", f"/holds/{hold['holdId']}/confirm", token=token)
    reservation_id = booked["reservationId"]
    print(f"   {reservation_id} {booked['status']}: {booked['machineLabel']} at {booked['laundromatName']}, "
          f"{booked['startTime']} (customer {email})", flush=True)

    print("3. Delete and recreate every container", flush=True)
    before = container_ids()
    compose("down")
    compose("up", "--detach", *services)
    api.wait_until_ready()
    kept = before & container_ids()
    if kept:
        raise CheckFailed(f"these containers were not recreated: {sorted(kept)}")
    print(f"   {len(before)} containers deleted, new ones started", flush=True)

    print("4. Read the booking back", flush=True)
    after = api.expect(200, "GET", f"/reservations/{reservation_id}", token=token)  # the old token: keys kept
    if after != booked:
        raise CheckFailed(f"the reservation changed across the restart:\n   before {booked}\n   after  {after}")
    mine = api.expect(200, "GET", "/me/reservations", token=token)["reservations"]
    if [r["reservationId"] for r in mine] != [reservation_id]:
        raise CheckFailed(f"GET /me/reservations lists {mine}, expected only {reservation_id}")
    api.expect(200, "POST", "/auth/login", body=login)  # the account survived too
    print(f"   {reservation_id} is still {after['status']}, unchanged; the old token and the login still work",
          flush=True)

    api.expect(204, "DELETE", f"/reservations/{reservation_id}", token=token)
    print(f"   cleaned up: {reservation_id} cancelled, its slot is free again", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that a booking survives recreating the containers.")
    parser.add_argument("services", nargs="*", help="compose services to start (default: all of them)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="where compose publishes the API")
    args = parser.parse_args()

    api = Api(args.base_url)
    print(f"Restart check (correlation id {api.correlation_id})", flush=True)
    try:
        run(api, args.services)
    except CheckFailed as failed:
        print(f"FAIL: {failed}", flush=True)
        return 1
    except subprocess.CalledProcessError as failed:
        print(f"FAIL: docker compose exited with {failed.returncode}", flush=True)
        return 1
    print("PASS: the booking survived the restart", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
