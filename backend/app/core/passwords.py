"""Password hashing with bcrypt. We store only the hash; the salt and cost are inside it."""
from functools import cached_property

import bcrypt

MAX_PASSWORD_BYTES = 72  # bcrypt reads at most 72 bytes; registration refuses longer passwords


class PasswordHasher:
    """rounds is bcrypt's cost (2^rounds iterations). 12 takes about 0.25 s; tests use 4 to stay fast.

    verify() works on a hash made with any cost, because the cost is stored in the hash.
    """

    def __init__(self, rounds: int = 12):
        self.rounds = rounds

    def hash(self, password: str) -> str:
        encoded = password.encode()
        if len(encoded) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password is longer than {MAX_PASSWORD_BYTES} bytes")
        return bcrypt.hashpw(encoded, bcrypt.gensalt(self.rounds)).decode()

    def verify(self, password: str, password_hash: str) -> bool:
        encoded = password.encode()
        if len(encoded) > MAX_PASSWORD_BYTES:
            return False  # could never have been registered
        return bcrypt.checkpw(encoded, password_hash.encode())

    def verify_nothing(self, password: str) -> None:
        """Do the work of one verify() against a throwaway hash.

        Login calls this when the email is unknown, so a wrong email takes as long as a wrong
        password and response times don't reveal which emails have accounts.
        """
        self.verify(password, self._dummy_hash)

    @cached_property
    def _dummy_hash(self) -> str:
        return self.hash("not-a-real-password")
