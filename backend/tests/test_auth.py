"""Authentication and the NFR-001 acceptance test (#20).

The old stub trusted an `X-Org-Id` header, so "org isolation" was a filter
applied to whatever tenant the caller named. These tests are written against
that specific failure: the header must no longer do anything, the org must come
from a signature, and one org's decisions must not be visible to another.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import DEFAULT_ITERATIONS, hash_password, verify_password
from app.auth.tokens import InvalidToken, create_access_token, decode_access_token
from app.config import DEV_JWT_SECRET, settings
from app.data.synthetic import DEFAULT_ORG_ID
from app.main import app
from tests.support import auth_headers, authenticated_client, token_for

# Every tenant-scoped endpoint. NFR-001's acceptance criterion is zero
# cross-tenant leaks across *all* of them, so the list is the test's subject
# rather than a sample — a new endpoint added without auth shows up here.
TENANT_SCOPED_GET_ENDPOINTS = [
    "/api/action-queue",
    "/api/summary",
    "/api/forecast",
    "/api/invoice/INV-1042",
    "/api/invoice/INV-1042/draft",
    "/api/invoice/INV-1042/artifact",
]

TENANT_SCOPED_POST_ENDPOINTS = [
    "/api/actions/INV-1042/approve",
    "/api/actions/INV-1042/reject",
]


# --------------------------------------------------------------- passwords


def test_password_round_trips():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)


def test_wrong_password_is_rejected():
    stored = hash_password("correct horse battery staple")
    assert not verify_password("Correct horse battery staple", stored)


def test_hash_is_salted_so_equal_passwords_differ():
    """Two users with the same password must not share a digest."""
    assert hash_password("same") != hash_password("same")


def test_hash_records_its_own_iteration_count():
    """Raising the cost later must not invalidate existing hashes."""
    assert hash_password("x").split("$")[1] == str(DEFAULT_ITERATIONS)


def test_malformed_hash_fails_instead_of_raising():
    assert not verify_password("anything", "not-a-real-hash")


# --------------------------------------------------------------- tokens


def test_token_round_trips_the_org():
    token = create_access_token(
        user_id="USR-1", org_id="ORG-A", email="a@x.test", secret="s" * 32, ttl_minutes=5
    )
    claims = decode_access_token(token, secret="s" * 32)
    assert claims["org"] == "ORG-A"
    assert claims["sub"] == "USR-1"


def test_token_signed_with_another_key_is_rejected():
    token = create_access_token(
        user_id="USR-1", org_id="ORG-A", email="a@x.test", secret="s" * 32, ttl_minutes=5
    )
    with pytest.raises(InvalidToken):
        decode_access_token(token, secret="different" * 4)


def test_expired_token_is_rejected():
    token = create_access_token(
        user_id="USR-1", org_id="ORG-A", email="a@x.test", secret="s" * 32, ttl_minutes=-1
    )
    with pytest.raises(InvalidToken):
        decode_access_token(token, secret="s" * 32)


def test_unsigned_token_is_rejected():
    """The alg=none confusion attack: a token asking to be trusted unverified."""
    forged = jwt.encode({"sub": "USR-1", "org": "ORG-EVIL"}, key="", algorithm="none")
    with pytest.raises(InvalidToken):
        decode_access_token(forged, secret="s" * 32)


def test_token_without_an_org_claim_is_rejected():
    """A validly signed token still cannot reach org_scoped without a tenant."""
    token = jwt.encode(
        {"sub": "USR-1", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        decode_access_token(token, secret=settings.jwt_secret)


def test_dev_signing_key_is_long_enough_for_hs256():
    """RFC 7518 §3.2 requires at least 32 bytes for HS256."""
    assert len(DEV_JWT_SECRET.encode()) >= 32


# --------------------------------------------------------------- endpoints


@pytest.mark.parametrize("path", TENANT_SCOPED_GET_ENDPOINTS)
def test_endpoints_require_a_token(path):
    assert TestClient(app).get(path).status_code == 401


@pytest.mark.parametrize("path", TENANT_SCOPED_POST_ENDPOINTS)
def test_decision_endpoints_require_a_token(path):
    assert TestClient(app).post(path).status_code == 401


@pytest.mark.parametrize("path", TENANT_SCOPED_GET_ENDPOINTS)
def test_x_org_id_header_no_longer_grants_access(path):
    """The exact hole #20 was opened for.

    Setting the header used to be sufficient to be treated as that org. It must
    now be inert — present, ignored, and still unauthorized.
    """
    response = TestClient(app).get(path, headers={"X-Org-Id": "ORG-DEMO"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", TENANT_SCOPED_GET_ENDPOINTS)
def test_garbage_token_is_rejected(path):
    response = TestClient(app).get(path, headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


def test_expired_token_is_rejected_at_the_endpoint():
    client = TestClient(app, headers={"Authorization": f"Bearer {token_for(ttl_minutes=-1)}"})
    assert client.get("/api/action-queue").status_code == 401


def test_health_stays_public():
    """A liveness probe that needs a credential is not a liveness probe."""
    assert TestClient(app).get("/health").status_code == 200


def test_valid_token_is_admitted():
    assert authenticated_client().get("/api/action-queue").status_code == 200


# --------------------------------------------------- NFR-001 cross-tenant


def test_one_orgs_decision_is_invisible_to_another():
    """NFR-001 acceptance: zero cross-tenant leaks.

    The same invoice id exists in both orgs' synthetic portfolios, which is the
    hard case — isolation cannot come from the id being unguessable.
    """
    ours = authenticated_client("ORG-DEMO")
    theirs = authenticated_client("ORG-OTHER")

    approved = ours.post("/api/actions/INV-1042/approve")
    assert approved.status_code == 200
    assert approved.json()["approvalState"] == "APPROVED"

    other_view = theirs.get("/api/invoice/INV-1042")
    assert other_view.status_code == 200
    assert other_view.json()["approvalState"] == "PENDING_APPROVAL"

    # And the other org must not inherit the audit trail behind that decision.
    assert not [
        entry
        for entry in other_view.json()["auditTrail"]
        if entry["decidedBy"] == "HUMAN"
    ]


def test_the_deciding_org_still_sees_its_own_decision():
    """The isolation above must not be achieved by losing the decision."""
    ours = authenticated_client("ORG-DEMO")
    ours.post("/api/actions/INV-1042/approve")

    assert ours.get("/api/invoice/INV-1042").json()["approvalState"] == "APPROVED"


def test_actor_comes_from_the_token_not_the_request():
    """FR-014 asks who decided; a caller must not be able to sign as someone else."""
    client = authenticated_client(DEFAULT_ORG_ID, email="real@lienrho.local")

    response = client.post("/api/actions/INV-1042/approve?actor=someone-else")

    human = [e for e in response.json()["auditTrail"] if e["decidedBy"] == "HUMAN"]
    assert human, "expected a HUMAN audit entry"
    assert "real@lienrho.local" in human[-1]["why"]
    assert "someone-else" not in human[-1]["why"]


def test_auth_headers_helper_produces_an_accepted_token():
    response = TestClient(app).get("/api/action-queue", headers=auth_headers())
    assert response.status_code == 200
