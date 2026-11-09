"""What use cases hand out: plain data shaped like the contract, camelCase on the wire.

It lives here and not in app/api/schemas because services may not import the interface layer.
A route returns `to_response(service.something(...))` and the DTO is serialized as is.
"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Dto(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, frozen=True)
