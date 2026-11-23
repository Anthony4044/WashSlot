"""[T.8.3.1] FastAPI's generated OpenAPI (/docs) must match the authored contract.

Same paths, methods and status codes, and every request and response body has the same fields and the
same required fields. Any drift fails CI: then fix the code, or change the contract first.

Two differences are allowed, because they are not on the wire:
- path parameter names ({slot_id} in Python, {slotId} in the contract): both become "{}" here;
- "default" (5xx): only the contract has it, FastAPI cannot document it.
"""
import re

from app.main import create_app
from tests.test_contract import CONTRACT, METHODS

GENERATED = create_app().openapi()


def resolve(doc: dict, node: dict) -> dict:
    while "$ref" in node:
        target = doc
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def shape(doc: dict, schema: dict):
    """The fields of a schema, nested: {"field": ..., "required": [...]}. Leaves are None."""
    schema = resolve(doc, schema)
    if "anyOf" in schema:  # FastAPI writes "X or null" as anyOf; the null half adds no fields
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return shape(doc, options[0])
    if "properties" in schema:
        fields = {name: shape(doc, value) for name, value in schema["properties"].items()}
        return {**fields, "required": sorted(schema.get("required", []))}
    if schema.get("type") == "array":
        return [shape(doc, schema["items"])]
    return None


def body(doc: dict, part: dict):
    content = resolve(doc, part).get("content", {}).get("application/json")
    return shape(doc, content["schema"]) if content else None


def operations(doc: dict) -> dict:
    found = {}
    for path, item in doc["paths"].items():
        for method in METHODS:
            if method in item:
                op = item[method]
                name = f"{method.upper()} {re.sub(r'{[^}]*}', '{}', path)}"
                found[name] = {status: body(doc, r) for status, r in op["responses"].items() if status != "default"}
                if "requestBody" in op:
                    found[name]["request"] = body(doc, op["requestBody"])
    return found


def test_same_version():
    assert GENERATED["info"]["version"] == CONTRACT["info"]["version"]


def test_same_operations():
    assert sorted(operations(GENERATED)) == sorted(operations(CONTRACT))


def test_same_status_codes_and_bodies():
    generated, contract = operations(GENERATED), operations(CONTRACT)
    for name in contract:
        assert generated.get(name) == contract[name], name


def test_every_response_documents_the_correlation_header():
    for document in (CONTRACT, GENERATED):
        for item in document["paths"].values():
            for method in METHODS:
                if method in item:
                    for response in item[method]["responses"].values():
                        resolved = resolve(document, response)
                        header = resolve(document, resolved["headers"]["X-Correlation-ID"])
                        assert header["required"] is True
                        assert header["schema"]["maxLength"] == 64
