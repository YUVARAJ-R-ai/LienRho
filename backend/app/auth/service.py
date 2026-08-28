"""Reading and writing users and orgs (#20).

Kept separate from the router so the login flow can be tested without going
through HTTP, and so seeding a demo org reuses exactly the code that serves a
real registration rather than a parallel path that could drift from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.db.models import Org, User


@dataclass(frozen=True)
class AuthenticatedUser:
    """What the rest of the app is allowed to know about the caller."""

    user_id: str
    org_id: str
    email: str
    display_name: str


class EmailAlreadyRegistered(Exception):
    """Raised when a registration reuses an existing email."""


def create_org(session: Session, *, org_id: str, org_name: str) -> Org:
    """Create a tenant, or return the existing one with that id."""
    existing = session.get(Org, org_id)
    if existing is not None:
        return existing

    org = Org(
        org_id=org_id,
        org_name=org_name,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(org)
    session.flush()
    return org


def create_user(
    session: Session,
    *,
    org_id: str,
    email: str,
    password: str,
    display_name: str | None = None,
) -> AuthenticatedUser:
    """Register one user against an existing org."""
    email = email.strip().lower()
    if _find_by_email(session, email) is not None:
        raise EmailAlreadyRegistered(email)

    user = User(
        user_id=f"USR-{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or email.split("@")[0],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(user)
    session.flush()
    return _to_authenticated(user)


def authenticate(session: Session, *, email: str, password: str) -> AuthenticatedUser | None:
    """Return the user when the credentials are right, None otherwise.

    An unknown email still runs a password verification against a dummy hash.
    Returning early would make "no such user" measurably faster than "wrong
    password", which turns the login endpoint into an account enumerator.
    """
    user = _find_by_email(session, email.strip().lower())

    if user is None:
        verify_password(password, _dummy_hash())
        return None

    if not verify_password(password, user.password_hash):
        return None

    return _to_authenticated(user)


def _find_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _to_authenticated(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user.user_id,
        org_id=user.org_id,
        email=user.email,
        display_name=user.display_name,
    )


@cache
def _dummy_hash() -> str:
    """A throwaway hash at the real iteration count, computed once.

    The cost has to match a genuine verification or the comparison above buys
    nothing — a cheap dummy would still return faster for an unknown email and
    leave the enumeration timing signal intact. Built lazily so the ~0.3s of
    PBKDF2 lands on the first failed login rather than on every import,
    including the test suite's.
    """
    return hash_password("not-a-real-password")
