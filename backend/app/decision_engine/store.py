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

Choosing the store is deliberate rather than automatic: `settings.audit_store`
selects it, and an unreachable database raises instead of quietly degrading. An
audit trail that silently stops being durable is worse than one that fails
loudly, because nothing downstream can tell the difference until it is needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.decision_engine.engine import ApprovalState, AuditEntry, RecommendedAction


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


def get_approval_store() -> ApprovalStore:
    """The store this process uses, chosen once from `settings.audit_store`.

    Cached because `SqlApprovalStore` holds a session factory; the underlying
    engine pools connections, so this is not a per-request cost.
    """
    global _STORE
    if _STORE is None:
        from app.config import settings

        _STORE = (
            SqlApprovalStore()
            if settings.audit_store == "postgres"
            else InMemoryApprovalStore()
        )
    return _STORE


def set_approval_store(store: ApprovalStore | None) -> None:
    """Override the process store. For tests and for the demo reset path."""
    global _STORE
    _STORE = store
