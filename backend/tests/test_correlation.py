"""Request IDs must survive errors and stay isolated across concurrent requests."""
import asyncio
import io
import json
import logging
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, correlation_id
from app.main import create_app


@pytest.fixture
def json_logs(caplog):
    caplog.set_level(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    yield stream
    logging.getLogger().removeHandler(handler)
    handler.close()


def test_header_and_json_logs_share_the_supplied_id(json_logs):
    app = create_app()

    @app.get("/trace")
    def trace():
        logging.getLogger("trace-test").info("inside endpoint")
        return {"ok": True}

    response = TestClient(app).get("/trace", headers={"X-Correlation-ID": "booking-123"})
    assert response.headers["X-Correlation-ID"] == "booking-123"
    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    endpoint = next(entry for entry in entries if entry["message"] == "inside endpoint")
    completed = next(entry for entry in entries if entry["message"] == "request completed")
    assert endpoint["correlationId"] == completed["correlationId"] == "booking-123"
    assert (completed["method"], completed["path"], completed["status"]) == ("GET", "/trace", 200)
    assert completed["durationMs"] >= 0
    assert correlation_id.get() is None


@pytest.mark.parametrize("value", [None, "", "with spaces", "x" * 65])
def test_missing_or_invalid_id_is_replaced(value):
    headers = {} if value is None else {"X-Correlation-ID": value}
    client = TestClient(create_app())
    first = client.get("/health/live", headers=headers)
    second = client.get("/health/live", headers=headers)
    assert UUID(first.headers["X-Correlation-ID"]).version == 4
    assert first.headers["X-Correlation-ID"] != second.headers["X-Correlation-ID"]


@pytest.mark.parametrize("path,status", [("/missing", 404), ("/crash", 500)])
def test_error_responses_and_logs_keep_the_id(path, status, json_logs):
    app = create_app()

    @app.get("/crash")
    def crash():
        raise RuntimeError("a failure")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(path, headers={"X-Correlation-ID": "error-trace"})
    assert response.status_code == status
    assert response.headers["X-Correlation-ID"] == "error-trace"
    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    request_logs = [entry for entry in entries if entry["logger"].startswith("app.")]
    assert request_logs
    assert all(entry["correlationId"] == "error-trace" for entry in request_logs)
    assert next(entry for entry in request_logs if entry["message"] == "request completed")["status"] == status


def test_concurrent_requests_have_separate_contexts(json_logs):
    async def run():
        app = create_app()
        both_started = asyncio.Event()
        started = 0

        @app.get("/trace")
        async def trace():
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=2)
            logging.getLogger("concurrent-trace").info("inside endpoint")
            return {"correlationId": correlation_id.get()}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            return await asyncio.gather(
                client.get("/trace", headers={"X-Correlation-ID": "first"}),
                client.get("/trace", headers={"X-Correlation-ID": "second"}),
            )

    first, second = asyncio.run(run())
    assert first.json() == {"correlationId": "first"}
    assert second.json() == {"correlationId": "second"}
    entries = [json.loads(line) for line in json_logs.getvalue().splitlines()]
    assert {entry["correlationId"] for entry in entries if entry["logger"] == "concurrent-trace"} == {"first", "second"}
    assert correlation_id.get() is None


def test_cors_exposes_the_correlation_header():
    response = TestClient(create_app()).get("/health/live", headers={
        "Origin": "http://localhost:5173", "X-Correlation-ID": "browser-trace",
    })
    assert "X-Correlation-ID" in response.headers["Access-Control-Expose-Headers"]
