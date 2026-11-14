"""Turn a service Outcome into an HTTP response - the interface layer's one job."""
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.api.errors import error_response
from app.services.outcome import Outcome


def to_response(outcome: Outcome, success_status: int = 200) -> Response:
    headers = {"Idempotency-Replayed": "true"} if outcome.replayed else None
    if not outcome.ok:
        return error_response(outcome.code or "internal_error", headers)
    if success_status == 204:
        return Response(status_code=204, headers=headers)
    return JSONResponse(status_code=success_status, content=_dump(outcome.value), headers=headers)


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    return jsonable_encoder(value)
