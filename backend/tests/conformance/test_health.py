import pytest

from tests.conformance.contract import check


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
def test_public_health_probe(api, path):
    response = api.get(path)
    assert response.status_code == 200
    assert check(response, path, "get") == {"status": "ok"}
