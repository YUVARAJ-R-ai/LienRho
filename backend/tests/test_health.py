from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_needs_no_credential():
    """A liveness probe that needs a token is not a liveness probe (#20)."""
    assert TestClient(app).get("/health").status_code == 200


def test_health_reports_the_audit_store():
    """The store degrades silently by design (#19), so /health has to say which.

    Without this a running API can look entirely healthy while dropping every
    decision on restart.
    """
    body = client.get("/health").json()

    assert set(body["auditStore"]) >= {"requested", "active", "durable"}
    assert body["auditStore"]["active"] in {"postgres", "memory"}
