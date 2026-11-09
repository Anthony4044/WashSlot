"""POST /auth/register and POST /auth/login. Thin: parse, call the service, map the Outcome."""
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
    return AuthService(uow_factory, hasher, tokens)


Service = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/register",
    status_code=201,
    response_model=UserDto,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a customer account",
)
def register(body: RegisterRequest, service: Service):
    """Not idempotent: a repeat with the same email is 409 email_taken (so a timed-out caller can just log in)."""
    return to_response(service.register(body.email, body.password), 201)


@router.post(
    "/login",
    response_model=TokenDto,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Exchange email and password for an access token",
)
def login(body: LoginRequest, service: Service):
    """Safe to retry: each call issues a fresh token and changes nothing else."""
    return to_response(service.login(body.email, body.password))
