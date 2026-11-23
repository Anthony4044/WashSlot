import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import correlation_context

log = logging.getLogger(__name__)
VALID_ID = re.compile(r"[!-~]{1,64}")


class CorrelationMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("X-Correlation-ID", "")
        value = supplied if VALID_ID.fullmatch(supplied) else str(uuid4())
        scope.setdefault("state", {})["correlation_id"] = value
        started = perf_counter()
        status = 500

        async def send_response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Correlation-ID"] = value
            await send(message)

        with correlation_context(value):
            try:
                await self.app(scope, receive, send_response)
            finally:
                log.info("request completed", extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "durationMs": round((perf_counter() - started) * 1000, 2),
                })
