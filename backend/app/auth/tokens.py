"""Signed access tokens carrying the org (NFR-001, #20).

The token is the only thing the API trusts to say which org a request belongs
to. `sub` is the user, `org` is the tenant, and `org` is what reaches
`org_scoped()` — so forging a tenant means forging a signature.

Decoding pins `algorithms=["HS256"]`. Accepting whatever the token's own header
asks for is the classic JWT algorithm-confusion hole: a token claiming
`"alg": "none"` would otherwise verify against nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"


class InvalidToken(Exception):
    """Raised for a token that is missing, malformed, expired, or unsigned."""


def create_access_token(
    *, user_id: str, org_id: str, email: str, secret: str, ttl_minutes: int
) -> str:
    """Issue a token for one authenticated user."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "org": org_id,
            "email": email,
            "iat": now,
            "exp": now + timedelta(minutes=ttl_minutes),
        },
        secret,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str, *, secret: str) -> dict:
    """Verify a token and return its claims.

    Every failure mode collapses into `InvalidToken`. Telling a caller *why*
    their token was rejected — bad signature vs. expired vs. malformed — is a
    small oracle, and the client's remedy is the same in every case: log in.
    """
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:  # covers expired, bad signature, malformed
        raise InvalidToken(str(exc)) from exc

    if not claims.get("org") or not claims.get("sub"):
        raise InvalidToken("token is missing the org or subject claim")

    return claims
