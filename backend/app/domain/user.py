"""The User aggregate, in the DOMAIN layer (lecture Ch. 5): an account, its role, and what that role may do.

Rules that live here, because they must hold no matter which "door" creates or reads a user
(the API, the seed script, a future admin tool):
- Registering always makes a CUSTOMER. An OPERATOR is created only by scripts/seed_users.py.
- Emails are compared lower-case, so A@x.com and a@x.com are the same account.
- Each role gets a fixed set of scopes (least privilege, Ch. 8). Browsing needs no token at all.

Dependency rule: this file imports nothing from the api, services or data layers, and knows nothing
about HTTP, JSON, SQL or tokens. Scopes are just strings here. CHECKING a token's scopes happens
in the interface layer (app/api/security.py).
"""
from dataclasses import dataclass

from app.domain.enums import UserRole

# Scopes name an action on a resource ("resource:action"), as in Ch. 8.
RESERVATIONS_READ = "reservations:read"  # see my holds and reservations
RESERVATIONS_WRITE = "reservations:write"  # hold, confirm, cancel, check in
OPERATOR_MANAGE = "operator:manage"  # run a laundromat: machines, slots, today's list

# Least privilege: each role gets only what it needs. A customer's token can't reach operator tools,
# so a stolen customer token can do less damage.
SCOPES_BY_ROLE: dict[UserRole, tuple[str, ...]] = {
    UserRole.CUSTOMER: (RESERVATIONS_READ, RESERVATIONS_WRITE),
    UserRole.OPERATOR: (RESERVATIONS_READ, RESERVATIONS_WRITE, OPERATOR_MANAGE),
}


def normalize_email(email: str) -> str:
    """The one place that decides when two emails are 'the same': trim spaces, compare lower-case."""
    return email.strip().lower()


@dataclass
class User:
    id: int | None  # None until the data layer saves it and the database gives it an id
    email: str
    password_hash: str  # bcrypt hash; the password itself is never stored
    role: UserRole = UserRole.CUSTOMER

    @classmethod
    def register(cls, email: str, password_hash: str) -> "User":
        """A new account from the sign-up form.

        There is deliberately NO role parameter: no caller can ask for an operator, even by mistake.
        (tests/test_service_auth.py checks that passing role= is a TypeError.)
        """
        return cls(id=None, email=normalize_email(email), password_hash=password_hash, role=UserRole.CUSTOMER)

    @property
    def scopes(self) -> tuple[str, ...]:
        """What this user's tokens will allow. Computed from the role, so it can't drift out of sync."""
        return SCOPES_BY_ROLE[self.role]
