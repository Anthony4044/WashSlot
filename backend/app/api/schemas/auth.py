"""Request bodies for /auth. Strict like every request: an unknown field such as "role" is 422."""
from typing import Annotated

from pydantic import Field, field_validator

from app.api.schemas.base import RequestModel
from app.core.passwords import MAX_PASSWORD_BYTES

MIN_PASSWORD_LENGTH = 8

# Deliberately loose: one @, something on each side, a dot in the domain. Real checking is the inbox.
Email = Annotated[str, Field(max_length=320, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")]


class RegisterRequest(RequestModel):
    email: Email
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, password: str) -> str:
        if len(password.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
        return password


class LoginRequest(RequestModel):
    # No format rules here: a malformed email or password is just wrong credentials.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
