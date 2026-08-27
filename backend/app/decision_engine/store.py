"""Where human decisions and their audit trails are kept (FR-014, NFR-007).

`build_action_queue` recomputes every recommendation from scratch on each
request, so a decision recorded on a recommendation object would vanish with it.
The decision has to live outside the derived queue and be replayed onto it —
that is what this module holds.

Two implementations behind one interface, the same pattern the investigator and
strategist use:

- `InMemoryApprovalStore` runs with no external dependency. It is the permanent
  fallback for tests and for a dev machine with no Postgres, not a placeholder.
- `SqlApprovalStore` is the durable path that makes FR-014 and NFR-007 actually
  hold across a restart.

Both satisfy `ApprovalStore` and are exercised by the same contract tests, so
the Decision Engine cannot tell them apart.

`settings.audit_store` chooses. When it asks for Postgres and Postgres is not
reachable, the process falls back to the in-memory store rather than refusing
to serve — the same shape as `LLMStrategist` falling back to rule-based, and
for the same reason: a teammate who has not started a database should still get
a working app.

The risk in that is real, though. An audit trail that stops being durable
without saying so is worse than one that fails loudly, because nothing
downstream can tell the difference until the trail is needed. So the fallback
is deliberately *not* silent: it logs a warning naming the reason, it is
recorded in `audit_store_status()`, and `/health` reports it. Degraded is a
state you can observe, not one you have to infer.

The choice is made once per process and then kept. Retrying per call would be
worse than either option: decisions written while the database was down would
sit in memory, invisible to a later read that reached a recovered database,
and the two halves of the trail would disagree.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.decision_engine.engine import ApprovalState, AuditEntry, RecommendedAction

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRecord:
    """One invoice's recorded decision, plus every audit line behind it."""

    state: ApprovalState
    entries: list[AuditEntry] = field(default_factory=list)
    recommended_action: RecommendedAction | None = None
    actor: str | None = None


class ApprovalStore(ABC):
    """The contract every store honours. Keep it this narrow."""

    @abstractmethod
    def get(self, org_id: str, invoice_id: str) -> ApprovalRecord | None: ...

    @abstractmethod
    def record(self, org_id: str, invoice_id: str, record: ApprovalRecord) -> None: ...

    @abstractmethod
    def clear(self, org_id: str | None = None) -> None:
        """Forget recorded decisions. For tests and demo resets."""


class InMemoryApprovalStore(ApprovalStore):
    """Process-local store. Resets on restart — that is its whole limitation."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ApprovalRecord] = {}

    def get(self, org_id: str, invoice_id: str) -> ApprovalRecord | None:
        record = self._records.get((org_id, invoice_id))
        if record is None:
            return None
        # Copy the entry list so a caller extending a recommendation's trail
        # cannot grow the stored history as a side effect.
        return ApprovalRecord(
            state=record.state,
            entries=list(record.entries),
            recommended_action=record.recommended_action,
            actor=record.actor,
        )

    def record(self, org_id: str, invoice_id: str, record: ApprovalRecord) -> None:
        self._records[(org_id, invoice_id)] = ApprovalRecord(
            state=record.state,
            entries=list(record.entries),
            recommended_action=record.recommended_action,
            actor=record.actor,
        )

    def clear(self, org_id: str | None = None) -> None:
        if org_id is None:
            self._records.clear()
            return
        for key in [k for k in self._records if k[0] == org_id]:
            del self._records[key]


class SqlApprovalStore(ApprovalStore):
    """Postgres-backed store: decisions and trails survive an API restart.

    Every read and write is filtered by `org_id` (NFR-001, BR-TENANT). The
    filter is applied here, in the data-access layer, rather than by each
    caller — no endpoint author has to remember it.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from app.db.session import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def probe(self) -> None:
        """Raise unless the database is reachable and the tables are there.

        Checked against `action_decisions` rather than `SELECT 1`: a database
        that is up but un-migrated would pass a bare connection check and then
        fail on the first approval, which is precisely the late failure the
        fallback exists to avoid.
        """
        from app.db.models import ActionDecision

        with self._session_factory() as session:
            session.execute(select(ActionDecision).limit(1)).first()

    def get(self, org_id: str, invoice_id: str) -> ApprovalRecord | None:
        from app.db.models import ActionDecision, AuditLogEntry

        with self._session_factory() as session:
            decision = session.execute(
                select(ActionDecision).where(
                    ActionDecision.org_id == org_id,
                    ActionDecision.invoice_id == invoice_id,
                )
            ).scalar_one_or_none()
            if decision is None:
                return None

            rows = (
                session.execute(
                    select(AuditLogEntry)
                    .where(
                        AuditLogEntry.org_id == org_id,
                        AuditLogEntry.invoice_id == invoice_id,
                    )
                    .order_by(AuditLogEntry.sequence)
                )
                .scalars()
                .all()
            )

            return ApprovalRecord(
                state=ApprovalState(decision.approval_state),
                entries=[
                    AuditEntry(
                        timestamp=r.timestamp,
                        decided_by=r.decided_by,
                        what=r.what,
                        why=r.why,
                    )
                    for r in rows
                ],
                recommended_action=(
                    RecommendedAction(decision.recommended_action)
                    if decision.recommended_action
                    else None
                ),
                actor=decision.decided_by,
            )

    def record(self, org_id: str, invoice_id: str, record: ApprovalRecord) -> None:
        from app.db.models import ActionDecision, AuditLogEntry

        with self._session_factory() as session:
            existing = session.execute(
                select(ActionDecision).where(
                    ActionDecision.org_id == org_id,
                    ActionDecision.invoice_id == invoice_id,
                )
            ).scalar_one_or_none()

            action = (
                record.recommended_action.value if record.recommended_action else None
            )
            # The caller passes the full history each time, so the stored trail is
            # replaced wholesale rather than appended to. Appending would double
            # every earlier entry on the second decision for the same invoice.
            session.execute(
                delete(AuditLogEntry).where(
                    AuditLogEntry.org_id == org_id,
                    AuditLogEntry.invoice_id == invoice_id,
                )
            )

            decided_by = record.actor or "unknown"

            if existing is None:
                session.add(
                    ActionDecision(
                        org_id=org_id,
                        invoice_id=invoice_id,
                        approval_state=record.state.value,
                        recommended_action=action,
                        decided_by=decided_by,
                        decided_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
            else:
                existing.approval_state = record.state.value
                existing.recommended_action = action
                existing.decided_by = decided_by
                existing.decided_at = datetime.now(UTC).replace(tzinfo=None)

            for seq, entry in enumerate(record.entries):
                session.add(
                    AuditLogEntry(
                        org_id=org_id,
                        invoice_id=invoice_id,
                        sequence=seq,
                        timestamp=entry.timestamp,
                        decided_by=entry.decided_by,
                        what=entry.what,
                        why=entry.why,
                    )
                )

            session.commit()

    def clear(self, org_id: str | None = None) -> None:
        from app.db.models import ActionDecision, AuditLogEntry

        with self._session_factory() as session:
            for model in (AuditLogEntry, ActionDecision):
                statement = delete(model)
                if org_id is not None:
                    statement = statement.where(model.org_id == org_id)
                session.execute(statement)
            session.commit()


_STORE: ApprovalStore | None = None
_DEGRADED_REASON: str | None = None


@dataclass(frozen=True)
class AuditStoreStatus:
    """What this process is actually doing with decisions, for `/health`."""

    requested: str
    active: str
    durable: bool
    degraded_reason: str | None = None


def get_approval_store() -> ApprovalStore:
    """The store this process uses, chosen once from `settings.audit_store`.

    Falling back rather than raising when Postgres is unreachable, so a missing
    database degrades the app instead of breaking it. The fallback is logged and
    reported by `audit_store_status()` — see the module docstring for why it is
    made once and kept.

    Cached because `SqlApprovalStore` holds a session factory; the underlying
    engine pools connections, so this is not a per-request cost.
    """
    global _STORE, _DEGRADED_REASON
    if _STORE is not None:
        return _STORE

    from app.config import settings

    if settings.audit_store != "postgres":
        _STORE = InMemoryApprovalStore()
        return _STORE

    candidate = SqlApprovalStore()
    try:
        candidate.probe()
    except Exception as exc:  # noqa: BLE001 - any failure to reach the DB degrades
        _DEGRADED_REASON = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "audit_store=postgres but the database is unreachable; falling back to "
            "in-memory. Approvals and audit trails will NOT survive a restart (#19). "
            "Reason: %s",
            _DEGRADED_REASON,
        )
        _STORE = InMemoryApprovalStore()
    else:
        _DEGRADED_REASON = None
        _STORE = candidate

    return _STORE


def audit_store_status() -> AuditStoreStatus:
    """Whether decisions are actually being persisted right now.

    Calls `get_approval_store()` so that asking the question resolves the store
    if nothing has yet — otherwise `/health` would report "memory" on a healthy
    deployment simply because no approval had happened.
    """
    from app.config import settings

    store = get_approval_store()
    durable = isinstance(store, SqlApprovalStore)
    return AuditStoreStatus(
        requested=settings.audit_store,
        active="postgres" if durable else "memory",
        durable=durable,
        degraded_reason=_DEGRADED_REASON,
    )


def set_approval_store(store: ApprovalStore | None) -> None:
    """Override the process store. For tests and for the demo reset path.

    Clears the degraded flag too: passing None asks for a clean re-resolve, and
    leaving a stale reason behind would have `/health` reporting a fallback that
    is no longer in effect.
    """
    global _STORE, _DEGRADED_REASON
    _STORE = store
    _DEGRADED_REASON = None
