from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Body of every error response. Use in route `responses={409: {"model": ErrorResponse}}`."""

    model_config = ConfigDict(extra="forbid")

    error: str  # a stable, machine-readable code from app/api/errors.py, never prose
