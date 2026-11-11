"""The conformance harness: judge a running server by contract/openapi.yaml alone.

It reads the contract, never the server's code (no `import app` anywhere in this folder), so it
would judge a Java implementation of WashSlot exactly the same way.

    response = api.get("/laundromats")
    body = check(response, "/laundromats", "get")      # fails unless the contract allows this response
"""
import json
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contract" / "openapi.yaml"
CONTRACT = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
ERROR_CODES = {e["code"] for e in CONTRACT["x-error-catalog"]}


def _resolve(node: dict) -> dict:
    """Follow a '#/components/...' $ref (used for shared responses like NotFound)."""
    while "$ref" in node:
        target = CONTRACT
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def documented_response(path: str, method: str, status: int) -> dict:
    """The contract's response for this status. A 5xx may fall back to `default`; nothing else may."""
    responses = CONTRACT["paths"][path][method.lower()]["responses"]
    key = str(status)
    if key not in responses:
        assert status >= 500 and "default" in responses, (
            f"{method.upper()} {path} returned {status}, which the contract does not allow "
            f"(documented: {', '.join(responses)})"
        )
        key = "default"
    return _resolve(responses[key])


def schema_for(path: str, method: str, status: int) -> dict | None:
    """The JSON Schema of the response body, with the components along so that $ref resolves."""
    content = documented_response(path, method, status).get("content")
    if content is None:
        return None
    return {**content["application/json"]["schema"], "components": CONTRACT["components"]}


def check(response: httpx.Response, path: str, method: str):
    """Assert the response is one the contract allows, and return its parsed body (or None)."""
    schema = schema_for(path, method, response.status_code)
    where = f"{method.upper()} {path} -> {response.status_code}"
    if schema is None:
        assert response.content == b"", f"{where}: the contract says no body, got {response.text!r}"
        return None

    assert response.headers.get("content-type", "").startswith("application/json"), f"{where}: not JSON"
    body = response.json()
    errors = sorted(Draft202012Validator(schema).iter_errors(body), key=lambda e: list(e.path))
    assert not errors, f"{where}: body breaks the contract:\n" + "\n".join(
        f"  at {'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors
    ) + f"\n  body: {json.dumps(body)[:500]}"
    if response.status_code >= 400:
        assert body["error"] in ERROR_CODES, f"{where}: error code {body['error']!r} is not in x-error-catalog"
    return body


def check_error(response: httpx.Response, path: str, method: str, status: int, code: str) -> None:
    """Assert an exact error: this status, this code, and a body the contract allows."""
    assert response.status_code == status, f"expected {status} {code}, got {response.status_code} {response.text}"
    assert check(response, path, method) == {"error": code}
