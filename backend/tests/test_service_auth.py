"""AuthService (register, login) against the in-memory unit of work. No database, no HTTP.

This works because the service layer never touches HTTP or SQL (lecture Ch. 5): it only talks to
a unit of work, and app/data/memory.py provides one that keeps everything in dictionaries.
The checks here are on Outcomes ("email_taken", "invalid_credentials"), never on status codes:
turning a code into 409 or 401 is the interface layer's job.
"""
import pytest

from app.domain.enums import UserRole
from app.domain.user import User
from app.services.auth import AuthService


@pytest.fixture
def service(memory_uow, password_hasher, access_tokens) -> AuthService:
    return AuthService(memory_uow, password_hasher, access_tokens)


def test_register_creates_a_customer(service, memory_uow):
    outcome = service.register("alice@example.com", "correct horse")
    assert outcome.ok
    assert outcome.value.model_dump(by_alias=True) == {"userId": "usr_1", "email": "alice@example.com",
                                                       "role": UserRole.CUSTOMER}
    stored = memory_uow.users.get_by_email("alice@example.com")
    assert stored.role == UserRole.CUSTOMER
    assert stored.password_hash != "correct horse" and stored.password_hash.startswith("$2b$")


def test_register_stores_the_email_lower_case(service):
    assert service.register("  Alice@Example.COM ", "correct horse").value.email == "alice@example.com"


@pytest.mark.parametrize("again", ["alice@example.com", "ALICE@example.com", " alice@EXAMPLE.com"])
def test_register_twice_is_email_taken(service, again):
    assert service.register("alice@example.com", "correct horse").ok
    outcome = service.register(again, "another password")
    assert not outcome.ok and outcome.code == "email_taken"


def test_login_returns_a_token_for_that_user(service, access_tokens):
    user_id = service.register("alice@example.com", "correct horse").value.user_id
    outcome = service.login("alice@example.com", "correct horse")
    assert outcome.ok
    dto = outcome.value
    assert dto.token_type == "Bearer" and dto.expires_in == 3600
    assert dto.scope == "reservations:read reservations:write"
    claims = access_tokens.verify(dto.access_token)
    assert claims.subject == user_id
    assert claims.scopes == {"reservations:read", "reservations:write"}


def test_login_ignores_email_case(service):
    service.register("alice@example.com", "correct horse")
    assert service.login(" ALICE@example.com", "correct horse").ok


def test_operator_token_adds_operator_manage(service, memory_uow, password_hasher, access_tokens):
    memory_uow.users.add(User(id=None, email="op@example.com", password_hash=password_hasher.hash("operator pw"),
                              role=UserRole.OPERATOR))
    dto = service.login("op@example.com", "operator pw").value
    assert dto.scope == "reservations:read reservations:write operator:manage"
    assert "operator:manage" in access_tokens.verify(dto.access_token).scopes


def test_wrong_password_is_invalid_credentials(service):
    service.register("alice@example.com", "correct horse")
    outcome = service.login("alice@example.com", "wrong horse")
    assert not outcome.ok and outcome.code == "invalid_credentials"


def test_unknown_email_is_the_same_invalid_credentials(service):
    outcome = service.login("nobody@example.com", "correct horse")
    assert not outcome.ok and outcome.code == "invalid_credentials"


def test_register_has_no_way_to_ask_for_a_role():
    with pytest.raises(TypeError):
        User.register("a@example.com", "hash", role=UserRole.OPERATOR)
