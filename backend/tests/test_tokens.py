"""Password hashing, token issuing and key handling, without HTTP. The attacks are in test_security.py."""
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.passwords import PasswordHasher
from app.core.tokens import AccessTokens, InvalidToken, MissingKeys, load_private_key, load_public_key
from scripts import generate_keys

# --- passwords ------------------------------------------------------------------------------

def test_hash_is_salted_and_verifies(password_hasher):
    first, second = password_hasher.hash("correct horse"), password_hasher.hash("correct horse")
    assert first != second  # a fresh salt every time
    assert password_hasher.verify("correct horse", first) and password_hasher.verify("correct horse", second)
    assert not password_hasher.verify("Correct horse", first)


def test_verify_reads_the_cost_from_the_hash(password_hasher):
    assert PasswordHasher(rounds=12).verify("correct horse", password_hasher.hash("correct horse"))


def test_passwords_longer_than_72_bytes_are_refused(password_hasher):
    too_long = "é" * 37  # 74 bytes in UTF-8, although only 37 characters
    with pytest.raises(ValueError):
        password_hasher.hash(too_long)
    assert not password_hasher.verify(too_long, password_hasher.hash("x" * 72))


# --- tokens ---------------------------------------------------------------------------------

def test_issued_token_verifies_with_its_claims(access_tokens):
    now = datetime.now(UTC).replace(microsecond=0)
    claims = access_tokens.verify(access_tokens.issue("usr_9", ("reservations:read",), now=now))
    assert claims.subject == "usr_9"
    assert claims.scopes == {"reservations:read"}
    assert claims.expires_at == now + timedelta(minutes=60)


def test_token_just_past_expiry_is_invalid(access_tokens):
    token = access_tokens.issue("usr_9", (), now=datetime.now(UTC) - timedelta(minutes=60, seconds=1))
    with pytest.raises(InvalidToken):
        access_tokens.verify(token)


def test_verify_only_instance_cannot_issue(access_tokens, rsa_key_pair):
    verifier = AccessTokens(public_key=load_public_key(rsa_key_pair[1]), issuer=access_tokens.issuer,
                            audience=access_tokens.audience, expires_minutes=60)
    assert verifier.verify(access_tokens.issue("usr_9", ())).subject == "usr_9"
    with pytest.raises(MissingKeys):
        verifier.issue("usr_9", ())


def test_small_rsa_keys_are_refused():
    weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pem = weak.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    with pytest.raises(ValueError):
        load_private_key(pem)


def test_missing_key_files_say_how_to_make_them(tmp_path):
    settings = Settings(jwt_private_key_file=tmp_path / "nope.pem", jwt_public_key_file=tmp_path / "nope.pub")
    with pytest.raises(MissingKeys, match="generate_keys.py"):
        AccessTokens.from_settings(settings)


# --- scripts/generate_keys.py ---------------------------------------------------------------

def test_generate_keys_writes_a_working_pair_and_keeps_it(tmp_path, monkeypatch):
    settings = Settings(jwt_private_key_file=tmp_path / "keys" / "private.pem",
                        jwt_public_key_file=tmp_path / "keys" / "public.pem")
    monkeypatch.setattr(generate_keys, "get_settings", lambda: settings)
    monkeypatch.setattr(generate_keys, "KEY_BITS", 2048)  # faster; the real default is 3072

    def run(*args: str) -> int:
        monkeypatch.setattr("sys.argv", ["generate_keys.py", *args])
        return generate_keys.main()

    assert run() == 0
    tokens = AccessTokens.from_settings(settings)
    assert tokens.verify(tokens.issue("usr_1", ())).subject == "usr_1"

    first = settings.jwt_private_key_file.read_bytes()
    assert run() == 0
    assert settings.jwt_private_key_file.read_bytes() == first  # not replaced without --force
    assert run("--force") == 0
    assert settings.jwt_private_key_file.read_bytes() != first
