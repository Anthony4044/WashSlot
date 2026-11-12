"""What use cases hand out: plain data shaped like the contract, camelCase on the wire.

"DTOs, not live objects" (lecture Ch. 5): a caller holding a live domain object could change it
behind the domain's rules, and the contract's shape must be free to differ from the domain's.

It lives here and not in app/api/schemas because services may not import the interface layer.
A route returns `to_response(service.something(...))` and the DTO is serialized as is.
"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Dto(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,  # user_id in Python, "userId" on the wire
        populate_by_name=True,
        serialize_by_alias=True,
        frozen=True,  # a DTO is a snapshot: nobody can change it after the service hands it out
        # A field with a default (TokenDto.token_type) is still always SENT, so the generated
        # /openapi.json must list it as required, as the contract does.
        json_schema_serialization_defaults_required=True,
    )
