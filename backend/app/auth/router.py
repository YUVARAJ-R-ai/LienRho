"""Login and identity endpoints (#20, NFR-001).

Deliberately small. Registration is not exposed as a public endpoint — orgs are
onboarded, not self-served, and an open `/auth/register` on a multi-tenant
system is a way to mint tenants nobody asked for. Seeding uses
`python -m app.auth.seed`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import authenticate
from app.auth.tokens import create_access_token
from app.config import settings
from app.db.scoping import Principal, get_current_principal
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: on a login the lookup either matches a stored
    # address or it does not, so format validation adds a dependency and an
    # extra way to reject a credential that was going to fail anyway.
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    org_id: str
    email: str
    display_name: str


class MeResponse(BaseModel):
    user_id: str
    org_id: str
    email: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange credentials for an access token carrying the org.

    One message for both "no such user" and "wrong password": distinguishing
    them tells an attacker which emails are registered.
    """
    user = authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        user_id=user.user_id,
        org_id=user.org_id,
        email=user.email,
        secret=settings.jwt_secret,
        ttl_minutes=settings.jwt_ttl_minutes,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_ttl_minutes * 60,
        org_id=user.org_id,
        email=user.email,
        display_name=user.display_name,
    )


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    """Who the current token says you are. Used by the frontend to gate screens."""
    return MeResponse(
        user_id=principal.user_id, org_id=principal.org_id, email=principal.email
    )
