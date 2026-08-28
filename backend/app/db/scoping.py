"""Org-scoped query helper and the identity behind it (NFR-001, BR-TENANT).

Endpoints must read/write through `org_scoped`, not raw `session.query`, so
tenant isolation isn't something every endpoint author has to remember.

The scoping half was always correct. What used to undermine it was the identity
feeding in: `get_current_org_id` trusted an `X-Org-Id` header, so any caller
could name any tenant and the filter would faithfully apply the wrong one. The
org now comes from a signed access token (#20), which is what makes NFR-001
actually hold rather than merely being expressed.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import InvalidToken, decode_access_token
from app.config import settings
from app.db.models import OrgScopedMixin

# auto_error=False so a missing header produces our own 401 with a WWW-Authenticate
# challenge, rather than FastAPI's bare 403 — which would tell a client its
# credentials were rejected when in fact it never sent any.
_bearer = HTTPBearer(auto_error=False)


class Principal:
    """The verified caller. Only ever constructed from a valid token."""

    __slots__ = ("email", "org_id", "user_id")

    def __init__(self, *, user_id: str, org_id: str, email: str) -> None:
        self.user_id = user_id
        self.org_id = org_id
        self.email = email


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve the caller from the bearer token, or reject the request."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(credentials.credentials, secret=settings.jwt_secret)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return Principal(
        user_id=claims["sub"], org_id=claims["org"], email=claims.get("email", "")
    )


def get_current_org_id(principal: Principal = Depends(get_current_principal)) -> str:
    """The tenant every query in this request must be filtered by."""
    return principal.org_id


def org_scoped(db: Session, model: type[OrgScopedMixin], org_id: str):
    """Return a SELECT for `model` pre-filtered to `org_id`."""
    return db.execute(select(model).where(model.org_id == org_id)).scalars()
