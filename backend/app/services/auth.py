"""The SERVICE layer for accounts (lecture Ch. 5): one method per use case, register and login.

What a service method does:
- runs one use case from start to finish: open a unit of work, ask repositories for domain
  objects, let the domain apply its rules, and return the result;
- returns an Outcome (app/services/outcome.py): success with a DTO, or failure with a stable error
  code such as "email_taken". It never returns an HTTP status. The service doesn't know that
  email_taken means 409; translating codes into statuses is the interface layer's job;
- hands out DTOs (plain data shaped like the contract), never live domain objects or database rows.

It never sees HTTP, JSON or SQL. So it can be tested with the in-memory unit of work
(tests/test_service_auth.py) with no server and no database.
"""
from typing import Literal

from app.core.passwords import PasswordHasher
from app.core.tokens import AccessTokens
from app.domain.enums import UserRole
from app.domain.user import User, normalize_email
from app.services.dto import Dto
from app.services.ids import USER, format_id
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory


class UserDto(Dto):
    """contract: User. On the wire: {"userId": "usr_9", "email": ..., "role": "CUSTOMER"} (camelCase by Dto)."""

    user_id: str  # the public id "usr_9"; the database's plain integer 9 never leaves the server
    email: str
    role: UserRole


class TokenDto(Dto):
    """contract: Token. On the wire: {"accessToken", "tokenType": "Bearer", "expiresIn", "scope"}."""

    access_token: str  # the JWT; the client sends it back as "Authorization: Bearer <accessToken>"
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int  # seconds until the token's exp claim
    scope: str  # space-separated, e.g. "reservations:read reservations:write"


def user_dto(user: User) -> UserDto:
    return UserDto(user_id=format_id(USER, user.id), email=user.email, role=user.role)


class AuthService:
    def __init__(self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, tokens: AccessTokens):
        self.uow_factory = uow_factory  # makes a fresh unit of work (one transaction) per use case
        self.hasher = hasher  # bcrypt
        self.tokens = tokens  # signs JWTs with the private key

    def register(self, email: str, password: str) -> Outcome:
        """Use case: create an account. Success -> UserDto; a taken email -> "email_taken".

        Always creates a CUSTOMER: there is no role parameter anywhere on this path.
        """
        # 1. Build the new User in the domain. Hash the password first: bcrypt is deliberately slow
        #    (~0.25 s), and doing it before the transaction keeps the transaction short.
        user = User.register(email, self.hasher.hash(password))

        # 2. Save it inside one unit of work (one database transaction, committed when the block ends).
        #    users.add() returns None if the email is already taken. The database's UNIQUE index decides
        #    that, so even two sign-ups racing for the same email produce exactly one account.
        with self.uow_factory() as uow:
            saved = uow.users.add(user)

        # 3. Answer with an Outcome: a stable error code, or the new account as a DTO.
        if saved is None:
            return Outcome.failure("email_taken")
        return Outcome.success(user_dto(saved))

    def login(self, email: str, password: str) -> Outcome:
        """Use case: check the credentials and issue an access token. Success -> TokenDto; else "invalid_credentials".

        This is AUTHENTICATION (Ch. 8, "who are you?"): the caller gives evidence (the password),
        and we answer with a signed token that says who they are and what they may do.
        """
        with self.uow_factory() as uow:
            user = uow.users.get_by_email(normalize_email(email))

        # A wrong email and a wrong password give the SAME answer, so an attacker can't use login to
        # find out which emails have accounts. verify_nothing() runs bcrypt anyway, so the two cases
        # also take about the same time and the response time doesn't give it away either.
        if user is None:
            self.hasher.verify_nothing(password)
            return Outcome.failure("invalid_credentials")
        if not self.hasher.verify(password, user.password_hash):
            return Outcome.failure("invalid_credentials")

        # The token carries the claims a protected endpoint checks later (app/core/tokens.py):
        #   sub   = who:            "usr_9"
        #   scope = what they may do: the role's scopes from the domain (least privilege, Ch. 8)
        # Signing with the PRIVATE key means nobody else can make or change one of these tokens.
        token = self.tokens.issue(format_id(USER, user.id), user.scopes)
        return Outcome.success(
            TokenDto(access_token=token, expires_in=self.tokens.expires_in_seconds, scope=" ".join(user.scopes))
        )
