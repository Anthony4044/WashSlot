"""Error catalog and handlers.

Every error leaves the API as {"error": "<code>"}: status codes route coarsely (4xx: fix the
request; 5xx: retry with the same Idempotency-Key), stable codes route finely.
The domain and services only name the code; THIS module is the one place that maps code -> status.
Clients must treat an unknown code as not retryable. Keep this catalog in sync with the contract.
"""
import logging
import re
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import correlation_context
from app.domain.errors import DomainError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    retryable: bool


CATALOG: dict[str, ErrorSpec] = {
    # request problems
    "invalid_request": ErrorSpec(422, False),
    "idempotency_key_required": ErrorSpec(422, False),
    "idempotency_key_reuse": ErrorSpec(422, False),  # same key, different body: a client bug
    "not_found": ErrorSpec(404, False),
    "method_not_allowed": ErrorSpec(405, False),
    # authentication (401: who are you?) and authorization (403: you may not)
    "missing_token": ErrorSpec(401, False),
    "invalid_token": ErrorSpec(401, False),
    "insufficient_scope": ErrorSpec(403, False),
    "invalid_credentials": ErrorSpec(401, False),  # login: wrong email or password (never says which)
    # state conflicts
    "slot_unavailable": ErrorSpec(409, False),
    "hold_expired": ErrorSpec(409, False),
    "too_late_to_cancel": ErrorSpec(409, False),
    "already_cancelled": ErrorSpec(409, False),
    "reservation_not_confirmed": ErrorSpec(409, False),
    "too_late_to_check_in": ErrorSpec(409, False),
    "email_taken": ErrorSpec(409, False),
    # our fault: the same request may succeed later
    "internal_error": ErrorSpec(500, True),
    "service_unavailable": ErrorSpec(503, True),
}

_STATUS_FALLBACK = {404: "not_found", 405: "method_not_allowed", 401: "missing_token", 403: "insufficient_scope"}
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")


class ApiError(Exception):
    """Interface-level refusal (e.g. a missing header or token). Raise with a catalog code."""

    def __init__(self, code: str, headers: dict[str, str] | None = None):
        super().__init__(code)
        self.code = code
        self.headers = headers


def error_response(code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    spec = CATALOG.get(code)
    if spec is None:  # a code nobody mapped is a bug: fail loudly, leak nothing
        log.error("Error code %r is not in the catalog (app/api/errors.py)", code)
        code, spec = "internal_error", CATALOG["internal_error"]
    return JSONResponse(status_code=spec.status, content={"error": code}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.code, exc.headers)

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError):
        return error_response(exc.code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) and _CODE.match(exc.detail) else None
        code = detail if detail in CATALOG else _STATUS_FALLBACK.get(exc.status_code, "invalid_request")
        return error_response(code, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return error_response("invalid_request")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # ServerErrorMiddleware runs outside user middleware, after its context has been reset.
        value = getattr(request.state, "correlation_id", None)
        with correlation_context(value):
            log.exception("Unhandled error", exc_info=exc)
        headers = {"X-Correlation-ID": value} if value else None
        return error_response("internal_error", headers)
