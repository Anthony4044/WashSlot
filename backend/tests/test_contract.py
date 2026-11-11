"""The authored contract (contract/openapi.yaml) is valid and keeps our own rules.

These tests read the contract file only; no server needed. The one exception is the error catalog,
which is compared with app/api/errors.py so the two lists can never drift apart.
(The conformance suite in tests/conformance/ is different: it never imports app.)
"""
from pathlib import Path

import yaml
from openapi_spec_validator import validate

from app.api.errors import CATALOG

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contract" / "openapi.yaml"
CONTRACT = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
METHODS = ("get", "put", "post", "delete", "patch")


def operations():
    for path, item in CONTRACT["paths"].items():
        for method in METHODS:
            if method in item:
                yield path, method, item[method]


def object_schemas(node, where="#"):
    """Every JSON Schema object with type: object, anywhere in the document."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield where, node
        for key, value in node.items():
            yield from object_schemas(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from object_schemas(value, f"{where}/{i}")


def test_contract_is_valid_openapi_3_1():
    validate(CONTRACT)
    assert CONTRACT["openapi"].startswith("3.1")


def test_every_object_schema_is_strict():
    for where, schema in object_schemas(CONTRACT):
        assert schema.get("additionalProperties") is False, f"{where}: needs additionalProperties: false"
        assert "required" in schema, f"{where}: needs a required list"


def test_every_id_has_a_prefix_pattern():
    schemas = CONTRACT["components"]["schemas"]
    ids = [name for name in schemas if name.endswith("Id")]
    assert ids
    for name in ids:
        assert schemas[name]["pattern"].endswith("_[1-9][0-9]*$"), name


def test_every_operation_says_how_to_retry():
    words = ("safe", "idempotent")
    for path, method, op in operations():
        description = op.get("description", "").lower()
        assert any(w in description for w in words), f"{method.upper()} {path}: say if it is safe or idempotent"


def test_every_operation_documents_errors_and_server_failures():
    for path, method, op in operations():
        assert "default" in op["responses"], f"{method.upper()} {path}: needs a default (5xx) response"
        if op.get("security") != []:
            for status in ("401", "403"):
                assert status in op["responses"], f"{method.upper()} {path}: protected, so document {status}"


def test_lists_are_wrapped_in_an_object():
    for path, method, op in operations():
        for status, response in op["responses"].items():
            schema = response.get("content", {}).get("application/json", {}).get("schema", {})
            assert schema.get("type") != "array", f"{method.upper()} {path} {status}: wrap the list in an object"


def test_error_catalog_matches_the_code():
    in_contract = {e["code"]: (e["status"], e["retryable"]) for e in CONTRACT["x-error-catalog"]}
    in_code = {code: (spec.status, spec.retryable) for code, spec in CATALOG.items()}
    assert in_contract == in_code
