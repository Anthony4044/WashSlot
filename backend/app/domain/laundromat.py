"""A laundromat: what browsing shows, plus who operates it (US-7.1)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Laundromat:
    id: int
    name: str
    address: str
    timezone: str
    operator_id: int | None = None  # the user who runs it; None until an operator is linked

    def is_run_by(self, user_id: int) -> bool:
        """THE ownership rule for operator tools: only the laundromat's own operator may change it."""
        return self.operator_id is not None and self.operator_id == user_id
