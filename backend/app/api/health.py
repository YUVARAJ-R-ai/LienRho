"""Liveness and the one piece of state worth reporting with it.

Public — a liveness probe that needs a credential is not a liveness probe.

It reports the audit store because that store degrades silently by design
(#19): when `audit_store=postgres` and Postgres is unreachable, the process
keeps serving on the in-memory fallback. That is the intended behaviour, but it
means a running, healthy-looking API can be dropping every decision on restart.
Somewhere has to say so out loud, and a log line scrolls past.

`status` stays "ok" while degraded. The API genuinely is up and every endpoint
works; it is durability that is reduced, and conflating the two would have a
monitor restart a service that is doing exactly what it was configured to do.
"""

from fastapi import APIRouter

from app.decision_engine.store import audit_store_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    store = audit_store_status()

    payload: dict = {
        "status": "ok",
        "auditStore": {
            "requested": store.requested,
            "active": store.active,
            "durable": store.durable,
        },
    }

    if store.degraded_reason is not None:
        payload["auditStore"]["degradedReason"] = store.degraded_reason
        payload["auditStore"]["warning"] = (
            "Approvals and audit trails are in memory and will not survive a restart."
        )

    return payload
