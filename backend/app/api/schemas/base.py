"""Base classes for request and response models (DTOs), and the shared Email type.

Python stays snake_case; JSON on the wire is camelCase, as in the contract (expiresAt, slotId).
"""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# contract: Email (used by RegisterRequest.email and HoldRequest.confirmationEmail).
# Deliberately loose: one @, something on each side, a dot in the domain. The only real proof that an
# email works is mail arriving in it. Spaces around it are allowed; each user of the type trims them.
Email = Annotated[str, Field(max_length=320, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")]


class ResponseModel(BaseModel):
    """A response DTO: plain data shaped like the contract. Never a domain object or a Row."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class RequestModel(BaseModel):
    """A request body. Strict: unknown fields are rejected."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
