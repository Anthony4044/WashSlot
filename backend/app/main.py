from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routes import auth, browse, health, holds, operator, reservations
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WashSlot API",
        version="1.1.0",  # the same as contract/openapi.yaml (tests/test_generated_openapi.py checks it)
        description=(
            "Reserve a specific washer or dryer in advance. The authored contract in contract/openapi.yaml "
            "is the source of truth; this generated document must conform to it."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # we use Bearer tokens, not cookies
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
        expose_headers=["Idempotency-Replayed", "X-Correlation-ID"],
    )
    register_error_handlers(app)

    # Routers: add one line per area, e.g.
    # from app.api.routes import auth
    # app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(browse.router)
    app.include_router(holds.router)
    app.include_router(reservations.router)
    app.include_router(operator.router)

    app.openapi = lambda: without_fastapi_422s(FastAPI.openapi(app))
    return app


def without_fastapi_422s(schema: dict) -> dict:
    """[T.8.3.1] Drop the 422 FastAPI documents on every route with a parameter.

    It shows FastAPI's {"detail": [...]} body, which we never send (errors.py sends {"error": "invalid_request"}).
    Routes that really answer 422 list it themselves, with ErrorResponse, so theirs stays.
    """
    for item in schema["paths"].values():
        for op in item.values():
            if "HTTPValidationError" in str(op["responses"].get("422")):
                del op["responses"]["422"]
    return schema


app = create_app()
