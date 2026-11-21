"""Sending one email through Resend (https://resend.com), the outside email service (US-6.1).

This is the only file that talks to Resend. It sends one email, or raises EmailSendError and
says whether trying again could help:

    network error, timeout, 5xx, 429 (too many requests)  -> retryable=True   (try again later)
    any other 4xx (bad address, bad API key, ...)          -> retryable=False  (give up now)

Every send carries an Idempotency-Key (our outbox id). If a send times out after Resend already
accepted it, our retry has the same key and Resend does not send the email twice.

Two switches for development and the demo:
- RESEND_API_KEY empty  -> nothing is sent; the email is written to the log instead.
- EMAIL_FAKE_FAILURES=N -> the first N sends fail on purpose (retryable), to show the retries.
"""
import logging
from functools import lru_cache

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


class EmailSendError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class ResendEmailSender:
    def __init__(self, api_key: str | None, from_address: str, fake_failures: int = 0,
                 http: httpx.Client | None = None):
        self.api_key = api_key
        self.from_address = from_address
        self.fake_failures_left = fake_failures
        self.http = http or httpx.Client(timeout=10)  # tests pass a fake client

    def send(self, to: str, subject: str, text: str, idempotency_key: str) -> None:
        # 1. The fake-failures switch, for tests and the demo.
        if self.fake_failures_left > 0:
            self.fake_failures_left -= 1
            raise EmailSendError("fake failure (EMAIL_FAKE_FAILURES)", retryable=True)

        # 2. No API key: development mode, just show the email in the log.
        if not self.api_key:
            log.info("RESEND_API_KEY is not set, so not sending. Email to %s: %s\n%s", to, subject, text)
            return

        # 3. The real call.
        try:
            response = self.http.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Idempotency-Key": idempotency_key},
                json={"from": self.from_address, "to": [to], "subject": subject, "text": text},
            )
        except httpx.HTTPError as error:  # no answer at all: network down, DNS, timeout
            raise EmailSendError(f"network error: {error!r}", retryable=True) from error

        if response.status_code < 300:
            return  # accepted
        retryable = response.status_code >= 500 or response.status_code == 429
        raise EmailSendError(f"Resend answered {response.status_code}: {response.text[:200]}", retryable)


@lru_cache
def get_email_sender() -> ResendEmailSender:
    """One sender per process, so the fake-failures count carries over between worker runs."""
    settings = get_settings()
    return ResendEmailSender(settings.resend_api_key, settings.email_from, settings.email_fake_failures)
