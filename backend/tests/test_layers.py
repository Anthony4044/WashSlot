"""The dependency rule: dependencies point inward.

The domain package must import no framework and no other layer.
These tests read the imports so a wrong import fails CI instead of slipping through review.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def imports_of(package: str) -> set[str]:
    found = set()
    for file in (APP / package).rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
    return found


def offenders(found: set[str], forbidden: tuple[str, ...]) -> set[str]:
    return {m for m in found if m.split(".")[0] in forbidden or m.startswith(forbidden)}


def test_domain_imports_no_framework_and_no_outer_layer():
    forbidden = ("fastapi", "starlette", "sqlalchemy", "pydantic", "alembic", "app.api", "app.data", "app.services")
    assert offenders(imports_of("domain"), forbidden) == set()


def test_services_do_not_know_http_or_sql():
    forbidden = ("fastapi", "starlette", "sqlalchemy", "app.api", "app.data")
    assert offenders(imports_of("services"), forbidden) == set()


def test_data_layer_does_not_know_http():
    forbidden = ("fastapi", "starlette", "app.api")
    assert offenders(imports_of("data"), forbidden) == set()
