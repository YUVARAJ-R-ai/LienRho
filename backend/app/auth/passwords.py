"""Password hashing (NFR-002).

PBKDF2-HMAC-SHA256 from the standard library rather than bcrypt or argon2.
Both of those are better algorithms, but both are native extensions, and this
project has already been bitten once by a native dependency that `uv sync`
cannot supply (xgboost/libomp — see CLAUDE.md). PBKDF2 at OWASP's recommended
iteration count is a sound choice that cannot break a teammate's setup.

The stored format carries its own iteration count, so raising the cost later
does not invalidate existing hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
# OWASP Password Storage Cheat Sheet, PBKDF2-HMAC-SHA256.
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Return a self-describing hash: algorithm$iterations$salt$digest."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash.

    Returns False rather than raising on a malformed hash: a corrupt row must
    fail the login, not crash the endpoint and reveal that it is corrupt.
    """
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, int(iterations)
    )
    # Constant-time: a timing difference here leaks the digest byte by byte.
    return hmac.compare_digest(candidate, expected)
