"""Password hashing for registered accounts.

Uses the standard library's maintained ``hashlib.pbkdf2_hmac`` implementation
(NIST SP 800-132) rather than a hand-rolled KDF, with a per-user random salt
and constant-time comparison via ``hmac.compare_digest``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
KEY_LENGTH_BYTES = 32


def hash_password(password: str) -> str:
    """Hash one password with PBKDF2-HMAC-SHA256 and a fresh salt.

    Args:
        password: Plaintext password; never stored or logged.

    Returns:
        A ``pbkdf2_sha256$iterations$salt_hex$digest_hex`` string.
    """

    salt_hex = secrets.token_hex(SALT_BYTES)
    digest_hex = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
        dklen=KEY_LENGTH_BYTES,
    ).hex()
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt_hex}${digest_hex}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify one password against a stored PBKDF2 hash.

    Args:
        password: Plaintext password to check.
        stored_hash: Previously stored hash from ``hash_password``.

    Returns:
        ``True`` when the password matches, compared in constant time.
    """

    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != PBKDF2_ALGORITHM:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
        dklen=len(bytes.fromhex(digest_hex)),
    ).hex()
    return hmac.compare_digest(computed, digest_hex)
