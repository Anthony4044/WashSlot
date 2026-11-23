from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.errors import ApiError
from app.api.schemas.errors import ErrorResponse
from app.data.database import postgres_is_ready

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


@router.get("/live", operation_id="live")
def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready", operation_id="ready", responses={503: {"model": ErrorResponse}})
def ready() -> HealthStatus:
    if not postgres_is_ready():
        raise ApiError("service_unavailable")
    return HealthStatus(status="ok")
