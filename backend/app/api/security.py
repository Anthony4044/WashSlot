"""Authentication and authorization as FastAPI dependencies (CODING_GUIDE section 8).

    @router.post("/slots/{slot_id}/holds")
    def place_hold(..., user: Annotated[CurrentUser, Depends(require_scope("reservations:write"))]):
        ...user.id...

- No Authorization header           -> 401 missing_token       ("we don't know who you are")
- Anything wrong with the token     -> 401 invalid_token       (never says what was wrong)
- Valid token without the scope     -> 403 insufficient_scope  ("we know you, but you may not")

The caller always comes from the verified token, never from the request body.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_access_tokens
from app.api.errors import ApiError
from app.core.tokens import AccessTokens, InvalidToken
from app.domain.errors import NotFound
from app.services.ids import USER, parse_id

# auto_error=False: we raise our own error codes instead of FastAPI's default 403.
# Declaring it still gives /docs its "Authorize" button.
_bearer = HTTPBearer(auto_error=False, description="Access token from POST /auth/login")


@dataclass(frozen=True)
class CurrentUser:
    id: int  # internal user id (the token's sub "usr_9" -> 9)
    scopes: frozenset[str]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    tokens: Annotated[AccessTokens, Depends(get_access_tokens)],
) -> CurrentUser:
    if credentials is None:
        # HTTPBearer gives None both when the header is absent and when it isn't "Bearer <token>".
        if request.headers.get("Authorization"):
            raise _invalid_token()
        raise ApiError("missing_token", {"WWW-Authenticate": "Bearer"})
    try:
        claims = tokens.verify(credentials.credentials)
        user_id = parse_id(USER, claims.subject)
    except (InvalidToken, NotFound):
        raise _invalid_token() from None
    return CurrentUser(id=user_id, scopes=claims.scopes)


def require_scope(scope: str) -> Callable[..., CurrentUser]:
    """A dependency that lets the request through only if the token carries `scope`."""

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.has_scope(scope):
            raise ApiError(
                "insufficient_scope", {"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{scope}"'}
            )
        return user

    return dependency


def _invalid_token() -> ApiError:
    return ApiError("invalid_token", {"WWW-Authenticate": 'Bearer error="invalid_token"'})
