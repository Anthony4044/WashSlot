"""Make the RSA key pair that signs (private) and verifies (public) access tokens.

From backend/:   python scripts/generate_keys.py           (keeps keys that already exist)
                 python scripts/generate_keys.py --force   (replaces them: every issued token stops working)

The files go where JWT_PRIVATE_KEY_FILE and JWT_PUBLIC_KEY_FILE point (default backend/keys/,
which is git-ignored). Never commit the private key. Each person generates their own.
"""
import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets "python scripts/..." import app

from app.core.config import get_settings  # noqa: E402

KEY_BITS = 3072


def generate_key_pair(bits: int = KEY_BITS) -> tuple[bytes, bytes]:
    """Return (private PEM, public PEM)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="replace existing keys")
    args = parser.parse_args()

    settings = get_settings()
    private_path, public_path = settings.jwt_private_key_file, settings.jwt_public_key_file
    existing = [p for p in (private_path, public_path) if p.exists()]
    if existing and not args.force:
        print(f"Keys already exist ({', '.join(map(str, existing))}). Use --force to replace them.")
        return 0

    private_pem, public_pem = generate_key_pair(KEY_BITS)
    for path in (private_path, public_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_pem)
    os.chmod(private_path, 0o600)  # owner-only on macOS/Linux; ignored on Windows
    public_path.write_bytes(public_pem)
    print(f"Wrote {private_path}\nWrote {public_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
