"""The JSON bodies of POST /auth/register and POST /auth/login, as Pydantic models.

Each model mirrors a schema in contract/openapi.yaml (RegisterRequest, LoginRequest). FastAPI
checks every request against it BEFORE our code runs, and any failure becomes 422 invalid_request
(the handler in app/api/errors.py).

Strict, like every request body (RequestModel sets extra="forbid", the contract says
additionalProperties: false): an unknown field is refused instead of silently ignored.
That is why {"email": ..., "password": ..., "role": "OPERATOR"} gets 422 and creates nothing.
"""
from pydantic import Field, field_validator

from app.api.schemas.base import Email, RequestModel
from app.core.passwords import MAX_PASSWORD_BYTES

MIN_PASSWORD_LENGTH = 8  # contract: RegisterRequest.password minLength: 8
# Email (in base.py) allows spaces around the address: registration trims them in normalize_email.


class RegisterRequest(RequestModel):
    """contract: RegisterRequest = {email, password}, both required, nothing else allowed."""

    email: Email
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, password: str) -> str:
        # bcrypt only reads the first 72 BYTES of a password, so two passwords that differ after
        # byte 72 would hash the same. We refuse them instead. Bytes, not characters: "é" is 2 bytes.
        if len(password.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
        return password


class LoginRequest(RequestModel):
    """contract: LoginRequest = {email, password}, both required, nothing else allowed.

    No format rules beyond "not empty": a badly formed email or a too-short password is simply wrong
    credentials (401), not a 422. Login must keep working for every existing account, even if the
    registration rules get stricter later (say, a 10-character minimum).
    """

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
