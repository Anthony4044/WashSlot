"""Contract first (lecture Ch. 2): the auth endpoints we serve are the ones contract/openapi.yaml defines.

The contract is the source of truth. FastAPI's generated /openapi.json must agree with it, not the
other way round. For POST /auth/register and POST /auth/login these tests compare the two: the same
operationId, only status codes the contract documents, and the same fields in the bodies.

No server and no database needed, so these run in CI on every PR. The conformance suite
(tests/conformance/test_auth.py) does the other half: it checks REAL responses from a running server.
"""
import pytest

from app.main import app
from tests.conformance.contract import CONTRACT

GENERATED = app.openapi()  # what FastAPI says we serve, built from our routes and Pydantic models
SUCCESS_STATUS = {"/auth/register": "201", "/auth/login": "200"}  # both operations are POST


def both(path: str) -> tuple[dict, dict]:
    """The operation as FastAPI generates it, and as the contract defines it."""
    return GENERATED["paths"][path]["post"], CONTRACT["paths"][path]["post"]


def body_schema(document: dict, holder: dict) -> dict:
    """The JSON body schema of a request body or response, following its $ref inside `document`."""
    name = holder["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
    return document["components"]["schemas"][name]


def fields(schema: dict) -> tuple[set[str], set[str]]:
    """(all property names, required property names)."""
    return set(schema["properties"]), set(schema.get("required", []))


@pytest.mark.parametrize("path", SUCCESS_STATUS)
def test_same_operation_id_and_public(path):
    ours, contract = both(path)
    assert ours["operationId"] == contract["operationId"]
    # Public: you need no token to get your first token.
    assert contract["security"] == []
    assert "security" not in ours


@pytest.mark.parametrize("path", SUCCESS_STATUS)
def test_only_status_codes_the_contract_documents(path):
    ours, contract = both(path)
    assert set(ours["responses"]) <= set(contract["responses"])


@pytest.mark.parametrize("path", SUCCESS_STATUS)
def test_request_body_has_exactly_the_contract_fields_and_is_strict(path):
    ours, contract = both(path)
    generated = body_schema(GENERATED, ours["requestBody"])
    assert fields(generated) == fields(body_schema(CONTRACT, contract["requestBody"]))
    assert generated["additionalProperties"] is False  # an unknown field (like "role") is refused, never ignored


@pytest.mark.parametrize("path, status", SUCCESS_STATUS.items())
def test_success_body_has_exactly_the_contract_fields(path, status):
    ours, contract = both(path)
    assert fields(body_schema(GENERATED, ours["responses"][status])) == fields(
        body_schema(CONTRACT, contract["responses"][status])
    )
