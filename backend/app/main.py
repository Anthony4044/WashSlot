from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WashSlot API",
        version="1.0.0",
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

    return app


app = create_app()
