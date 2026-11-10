"""Use cases: register an account, and log in to get an access token."""
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
    user_id: str  # "usr_9"
    email: str
    role: UserRole


class TokenDto(Dto):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int  # seconds
    scope: str  # space-separated, e.g. "reservations:read reservations:write"


def user_dto(user: User) -> UserDto:
    return UserDto(user_id=format_id(USER, user.id), email=user.email, role=user.role)


class AuthService:
    def __init__(self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, tokens: AccessTokens):
        self.uow_factory = uow_factory
        self.hasher = hasher
        self.tokens = tokens

    def register(self, email: str, password: str) -> Outcome:
        """Always creates a CUSTOMER. A taken email (in any letter case) is `email_taken`."""
        user = User.register(email, self.hasher.hash(password))  # hash first: keep the transaction short
        with self.uow_factory() as uow:
            saved = uow.users.add(user)
        if saved is None:
            return Outcome.failure("email_taken")
        return Outcome.success(user_dto(saved))

    def login(self, email: str, password: str) -> Outcome:
        """A wrong email and a wrong password both give `invalid_credentials`, in about the same time."""
        with self.uow_factory() as uow:
            user = uow.users.get_by_email(normalize_email(email))
        if user is None:
            self.hasher.verify_nothing(password)
            return Outcome.failure("invalid_credentials")
        if not self.hasher.verify(password, user.password_hash):
            return Outcome.failure("invalid_credentials")
        token = self.tokens.issue(format_id(USER, user.id), user.scopes)
        return Outcome.success(
            TokenDto(access_token=token, expires_in=self.tokens.expires_in_seconds, scope=" ".join(user.scopes))
        )
