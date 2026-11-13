"""Access tokens: JWTs signed with RS256 (CODING_GUIDE section 8).

Login signs with the PRIVATE key. Every other request verifies with the PUBLIC key, and the
verifier, not the token, picks the algorithm: algorithms=["RS256"], so `alg: none` and
HS256-signed-with-the-public-key tokens are refused. iss, aud and exp are always checked.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.core.config import Settings

ALGORITHM = "RS256"
MIN_KEY_BITS = 2048
_REQUIRED_CLAIMS = ["sub", "scope", "iss", "aud", "iat", "exp"]


class InvalidToken(Exception):
    """The token is malformed, forged, expired, or meant for someone else. Never says which."""


class MissingKeys(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    subject: str  # public user id, e.g. "usr_9"
    scopes: frozenset[str]
    expires_at: datetime


def load_private_key(pem: bytes) -> RSAPrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey) or key.key_size < MIN_KEY_BITS:
        raise ValueError(f"the private key must be RSA with at least {MIN_KEY_BITS} bits")
    return key


def load_public_key(pem: bytes) -> RSAPublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, RSAPublicKey) or key.key_size < MIN_KEY_BITS:
        raise ValueError(f"the public key must be RSA with at least {MIN_KEY_BITS} bits")
    return key


class AccessTokens:
    """Issues and verifies access tokens. Without a private key it can only verify."""

    def __init__(self, *, public_key: RSAPublicKey, private_key: RSAPrivateKey | None = None,
                 issuer: str, audience: str, expires_minutes: int):
        self._public_key = public_key
        self._private_key = private_key
        self.issuer = issuer
        self.audience = audience
        self.expires_in_seconds = expires_minutes * 60

    @classmethod
    def from_settings(cls, settings: Settings) -> "AccessTokens":
        return cls(
            public_key=load_public_key(_read_key(settings.jwt_public_key_file)),
            private_key=load_private_key(_read_key(settings.jwt_private_key_file)),
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expires_minutes=settings.jwt_expires_minutes,
        )

    def issue(self, subject: str, scopes: tuple[str, ...] | list[str], *, now: datetime | None = None) -> str:
        if self._private_key is None:
            raise MissingKeys("this AccessTokens has no private key, so it can only verify")
        issued_at = now or datetime.now(UTC)
        claims = {
            "sub": subject,
            "scope": " ".join(scopes),
            "iss": self.issuer,
            "aud": self.audience,
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=self.expires_in_seconds),
        }
        return jwt.encode(claims, self._private_key, algorithm=ALGORITHM)

    def verify(self, token: str) -> TokenClaims:
        """Every check, on every request (lecture Ch. 8). Any failure raises InvalidToken.

        Each line below is one check, and skipping it lets one attack through
        (each attack has its own test in tests/test_security.py).
        """
        try:
            claims = jwt.decode(
                token,
                self._public_key,  # 1. signature: only our private key could have made it  -> stops Attack A
                algorithms=[ALGORITHM],  # 2. we pick RS256, never the token's header  -> stops Attack B
                issuer=self.issuer,  # 3. iss: it was made by our login endpoint
                audience=self.audience,  # 4. aud: it was made for THIS API  -> stops Attack C
                options={"require": _REQUIRED_CLAIMS},  # 5. exp must be there (PyJWT checks it is in the future)
            )
        except jwt.InvalidTokenError as exc:  # bad signature, alg, iss, aud, exp, missing claim, garbage
            raise InvalidToken() from exc
        if not isinstance(claims["scope"], str):
            raise InvalidToken()
        return TokenClaims(
            subject=claims["sub"],
            scopes=frozenset(claims["scope"].split()),
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
        )


def _read_key(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise MissingKeys(
            f"JWT key file {path} not found. From backend/, run: python scripts/generate_keys.py"
        ) from None
