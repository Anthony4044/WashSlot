"""JSON logging and the correlation context shared by requests and outbox deliveries."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from json import dumps

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


@contextmanager
def correlation_context(value: str | None) -> Iterator[None]:
    token = correlation_id.set(value)
    try:
        yield
    finally:
        correlation_id.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": getattr(record, "correlation_id", correlation_id.get()),
        }
        for field in ("method", "path", "status", "durationMs", "outboxId", "reservationId", "attempt"):
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Uvicorn configures its own handlers before importing the application.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for existing in logging.getLogger(name).handlers:
            existing.setFormatter(JsonFormatter())
    # The middleware emits one request log with its correlation ID and elapsed time.
    logging.getLogger("uvicorn.access").disabled = True
