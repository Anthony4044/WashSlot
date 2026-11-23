"""The failed-email endpoints (US-7.3), judged by the contract alone.

Black-box: HTTP only, never `import app`. Access needs no data: no token is 401, and a customer
(registered through the API) gets 403. The operator's own calls log in as the seeded
operator@example.com (scripts/seed_users.py) and are skipped, saying why, when it isn't there.

They never retry a FAILED email: on a database with a real Resend key that would really send it.
Retrying a SENT one is safe (the contract says it changes nothing), so that is what we check.
"""
import pytest

from tests.conformance.contract import check, check_error

LIST = "/operator/notifications"
RETRY = "/operator/notifications/{notificationId}/retry"

EVERY_OPERATION = [("get", LIST, "/operator/notifications?status=FAILED"),
                   ("post", RETRY, "/operator/notifications/ntf_1/retry")]
IDS = ["listOperatorNotifications", "retryNotification"]


@pytest.fixture
def operator(api) -> dict[str, str]:
    r = api.post("/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    if r.status_code != 200:
        pytest.skip("no seeded operator@example.com: run scripts/seed_users.py and seed_laundromats.py")
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


@pytest.mark.parametrize(("method", "path", "url"), EVERY_OPERATION, ids=IDS)
def test_no_token_is_401(api, method, path, url):
    check_error(api.request(method.upper(), url), path, method, 401, "missing_token")


@pytest.mark.parametrize(("method", "path", "url"), EVERY_OPERATION, ids=IDS)
def test_a_customer_gets_403(api, customer, method, path, url):
    r = api.request(method.upper(), url, headers={"Authorization": customer["Authorization"]})
    check_error(r, path, method, 403, "insufficient_scope")


@pytest.mark.parametrize("status", [None, "FAILED", "PENDING", "SENT"])
def test_the_list_keeps_the_contract_and_the_filter(api, operator, status):
    params = {"status": status} if status else {}
    emails = check(api.get(LIST, params=params, headers=operator), LIST, "get")["notifications"]

    assert len(emails) <= 100
    if status:
        assert {e["status"] for e in emails} <= {status}


def test_an_unknown_status_is_422(api, operator):
    check_error(api.get(LIST, params={"status": "LOST"}, headers=operator), LIST, "get", 422, "invalid_request")


def test_retrying_an_unknown_email_is_404(api, operator):
    check_error(api.post("/operator/notifications/ntf_999999999/retry", headers=operator), RETRY, "post",
                404, "not_found")


def test_retrying_a_sent_email_changes_nothing(api, operator):
    sent = check(api.get(LIST, params={"status": "SENT"}, headers=operator), LIST, "get")["notifications"]
    if not sent:
        pytest.skip("the seeded operator has no SENT email yet: confirm a booking with the worker running")

    r = api.post(f"/operator/notifications/{sent[0]['notificationId']}/retry", headers=operator)

    assert check(r, RETRY, "post") == sent[0]  # idempotent: still SENT, nothing queued again
