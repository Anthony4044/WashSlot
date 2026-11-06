"""Base classes for request and response models (DTOs).

Python stays snake_case; JSON on the wire is camelCase, as in the contract (expiresAt, slotId).
"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ResponseModel(BaseModel):
    """A response DTO: plain data shaped like the contract. Never a domain object or a Row."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class RequestModel(BaseModel):
    """A request body. Strict: unknown fields are rejected."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
