"""The JSON body of POST /slots/{slotId}/holds, as a Pydantic model (contract: HoldRequest).

Strict like every request body: an unknown field is 422 invalid_request. So a caller can't send
{"confirmationEmail": ..., "userId": "usr_1"} to hold a slot for somebody else. WHO the hold is for
always comes from the verified token (lecture Ch. 8), never from the body.
"""
from pydantic import field_validator

from app.api.schemas.base import Email, RequestModel


class HoldRequest(RequestModel):
    """contract: HoldRequest = {confirmationEmail}, required, nothing else allowed."""

    # Where the confirmation email will be sent (US-6.1). The hold page prefills it with the login email.
    confirmation_email: Email

    @field_validator("confirmation_email")
    @classmethod
    def _trim(cls, email: str) -> str:
        return email.strip()  # " kim@example.com " is stored as "kim@example.com"
