"""POST /auth/register and POST /auth/login: the INTERFACE layer for accounts (lecture Ch. 5).

Contract first (Ch. 2): both operations were written in contract/openapi.yaml before this code
(operationIds `register` and `login`). This file implements them; it does not get to redefine them.
The conformance suite (tests/conformance/test_auth.py) checks the running server against that contract.

The interface layer has one job: translate between HTTP and the application.
    1. FastAPI parses and validates the JSON body (the Pydantic models in app/api/schemas/auth.py).
    2. We call ONE use case on the service layer (app/services/auth.py).
    3. to_response() turns the protocol-free Outcome into HTTP: a success becomes 201/200 with the
       DTO as JSON, an error code becomes {"error": "<code>"} with the status from the error catalog
       (app/api/errors.py: email_taken -> 409, invalid_credentials -> 401).
No business rule lives here. "Registering makes a CUSTOMER" is a domain rule (app/domain/user.py),
so it would still hold if a second door (an admin console, a CLI) were added later.

Both endpoints are public (`security: []` in the contract): you can't need a token to get your first token.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_access_tokens, get_password_hasher, get_uow_factory
from app.api.responses import to_response
from app.api.schemas.auth import LoginRequest, RegisterRequest
from app.api.schemas.errors import ErrorResponse
from app.core.passwords import PasswordHasher
from app.core.tokens import AccessTokens
from app.services.auth import AuthService, TokenDto, UserDto
from app.services.unit_of_work import UnitOfWorkFactory

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[AccessTokens, Depends(get_access_tokens)],
) -> AuthService:
    """Build the service from its parts. Tests swap the parts (test database, throwaway keys, fast bcrypt)."""
    return AuthService(uow_factory, hasher, tokens)


Service = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/register",
    operation_id="register",  # the same operationId as the contract
    status_code=201,
    response_model=UserDto,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a customer account",
)
def register(body: RegisterRequest, service: Service):
    """Contract responses: 201 User · 409 email_taken · 422 invalid_request.

    Ch. 3 classification: NOT idempotent. Sending it twice does not give the same result twice
    (the second call is 409 email_taken). So a caller whose request timed out should not retry it.
    It should log in with the same email and password; if that works, the account was created.

    The body has no "role" field, and unknown fields are refused with 422, so this endpoint can
    only ever create a CUSTOMER. Operators come from scripts/seed_users.py.
    """
    return to_response(service.register(body.email, body.password), 201)


@router.post(
    "/login",
    operation_id="login",  # the same operationId as the contract
    response_model=TokenDto,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Exchange email and password for an access token",
)
def login(body: LoginRequest, service: Service):
    """Contract responses: 200 Token · 401 invalid_credentials · 422 invalid_request.

    Ch. 3 classification: safe to retry. Each call only issues a fresh token and changes nothing
    else, so a caller whose request timed out can simply send it again.
    """
    return to_response(service.login(body.email, body.password))
