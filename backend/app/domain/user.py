"""The User aggregate: an account, its role, and what that role may do.

Rules that live here:
- Registering always makes a CUSTOMER. An OPERATOR is created only by scripts/seed_users.py.
- Emails are compared lower-case, so A@x.com and a@x.com are the same account.
- Each role gets a fixed set of scopes (least privilege: browsing needs no token at all).
"""
from dataclasses import dataclass

from app.domain.enums import UserRole

RESERVATIONS_READ = "reservations:read"
RESERVATIONS_WRITE = "reservations:write"
OPERATOR_MANAGE = "operator:manage"

SCOPES_BY_ROLE: dict[UserRole, tuple[str, ...]] = {
    UserRole.CUSTOMER: (RESERVATIONS_READ, RESERVATIONS_WRITE),
    UserRole.OPERATOR: (RESERVATIONS_READ, RESERVATIONS_WRITE, OPERATOR_MANAGE),
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass
class User:
    id: int | None  # None until the data layer saves it
    email: str
    password_hash: str
    role: UserRole = UserRole.CUSTOMER

    @classmethod
    def register(cls, email: str, password_hash: str) -> "User":
        """A new account from the sign-up form. There is no role parameter on purpose."""
        return cls(id=None, email=normalize_email(email), password_hash=password_hash, role=UserRole.CUSTOMER)

    @property
    def scopes(self) -> tuple[str, ...]:
        return SCOPES_BY_ROLE[self.role]
