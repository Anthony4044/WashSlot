import pytest

from tests.conformance.contract import check


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
def test_public_health_probe(api, path):
    response = api.get(path)
    assert response.status_code == 200
    assert check(response, path, "get") == {"status": "ok"}


def test_correlation_id_is_echoed(api):
    response = api.get("/health/live", headers={"X-Correlation-ID": "conformance-trace"})
    assert response.headers["X-Correlation-ID"] == "conformance-trace"
    check(response, "/health/live", "get")
