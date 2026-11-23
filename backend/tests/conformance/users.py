"""Make users through the API itself, as any outside client would."""
import uuid

PASSWORD = "conformance-pass-1"


def unique_email() -> str:
    return f"conf-{uuid.uuid4().hex[:12]}@example.com"


def new_customer(api) -> dict[str, str]:
    """Register and log in a fresh customer through the API: {"email", "Authorization"}."""
    email = unique_email()
    assert api.post("/auth/register", json={"email": email, "password": PASSWORD}).status_code == 201
    token = api.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["accessToken"]
    return {"email": email, "Authorization": f"Bearer {token}"}
