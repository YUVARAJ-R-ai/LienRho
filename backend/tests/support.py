"""Test helpers for authenticated requests (#20).

Tokens here are minted with the real `create_access_token` and verified by the
real dependency, so the tests exercise the actual auth path rather than an
override that stubs it out. Nothing here touches the database — token
verification is stateless by design, which is what lets the API suite keep
running with no Postgres.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.tokens import create_access_token
from app.config import settings
from app.data.synthetic import DEFAULT_ORG_ID
from app.main import app

DEMO_EMAIL = "tester@lienrho.local"


def token_for(org_id: str = DEFAULT_ORG_ID, *, email: str = DEMO_EMAIL, ttl_minutes: int = 60) -> str:
    """A valid signed token for one org."""
    return create_access_token(
        user_id=f"USR-{org_id}",
        org_id=org_id,
        email=email,
        secret=settings.jwt_secret,
        ttl_minutes=ttl_minutes,
    )


def auth_headers(org_id: str = DEFAULT_ORG_ID, *, email: str = DEMO_EMAIL) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(org_id, email=email)}"}


def authenticated_client(org_id: str = DEFAULT_ORG_ID, *, email: str = DEMO_EMAIL) -> TestClient:
    """A TestClient that sends a valid token on every request."""
    return TestClient(app, headers=auth_headers(org_id, email=email))
