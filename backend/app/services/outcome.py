from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Outcome:
    """Protocol-free result of a use case: success with a DTO, or a stable error code.

    No HTTP status here - the interface layer maps `code` to a status.
    `replayed` is set when an idempotent repeat is answered from the stored outcome.
    """

    ok: bool
    value: Any = None
    code: str | None = None
    replayed: bool = False

    @classmethod
    def success(cls, value: Any) -> "Outcome":
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, code: str) -> "Outcome":
        return cls(ok=False, code=code)
