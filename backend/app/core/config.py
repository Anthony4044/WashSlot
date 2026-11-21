"""App settings, read from environment variables or backend/.env. Nothing secret is hard-coded."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def to_sqlalchemy_url(url: str) -> str:
    """Neon gives 'postgresql://...'; SQLAlchemy needs the psycopg 3 driver named in the URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str | None = None
    test_database_url: str | None = None

    # JWT, signed RS256 with a key pair: the private key signs (login only),
    # the public key verifies. Verification also pins the algorithm and checks iss, aud and exp.
    jwt_private_key_file: Path = BACKEND_DIR / "keys" / "jwt_private.pem"
    jwt_public_key_file: Path = BACKEND_DIR / "keys" / "jwt_public.pem"
    jwt_issuer: str = "https://auth.washslot.local"
    jwt_audience: str = "https://api.washslot.local"
    jwt_expires_minutes: int = 60

    # Confirmation emails (US-6.1). Without an API key the worker only logs the email.
    resend_api_key: str | None = None
    email_from: str = "WashSlot <onboarding@resend.dev>"  # Resend's test sender works without a domain
    email_fake_failures: int = 0  # > 0: the first N sends fail on purpose (tests and the demo)

    cors_origins: str = "http://localhost:5173"
    hold_minutes: int = 10
    idempotency_retention_hours: int = 24  # promised in the contract

    @field_validator("jwt_private_key_file", "jwt_public_key_file")
    @classmethod
    def _relative_to_backend(cls, path: Path) -> Path:
        """keys/jwt_public.pem in .env means backend/keys/jwt_public.pem, from any working directory."""
        return path if path.is_absolute() else BACKEND_DIR / path

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
