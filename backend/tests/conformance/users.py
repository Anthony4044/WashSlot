"""Make users through the API itself, as any outside client would."""
import uuid

PASSWORD = "conformance-pass-1"


def unique_email() -> str:
    return f"conf-{uuid.uuid4().hex[:12]}@example.com"
