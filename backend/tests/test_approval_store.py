"""One contract, both stores (FR-014, NFR-007, #19).

Every test here runs twice — once against `InMemoryApprovalStore`, once against
`SqlApprovalStore`. That is the point: the Decision Engine must not be able to
tell them apart, so the fallback and the durable path are held to the same
behaviour rather than the fallback being tested and the real one assumed.

The SQL parameterisation skips when no database is reachable, so `pytest` still
passes on a clean clone.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.decision_engine.engine import ApprovalState, AuditEntry, RecommendedAction
from app.decision_engine.store import (
    ApprovalRecord,
    InMemoryApprovalStore,
    SqlApprovalStore,
)

ORG = "ORG-DEMO"
OTHER_ORG = "ORG-OTHER"


def _database_available() -> bool:
    try:
        engine = create_engine(settings.database_url)
        with engine.connect():
            return True
    except Exception:  # noqa: BLE001 - any failure to connect means "skip"
        return False


def _sql_store() -> SqlApprovalStore:
    engine = create_engine(settings.database_url)
    return SqlApprovalStore(sessionmaker(bind=engine, autoflush=False, autocommit=False))


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param(
            "postgres",
            id="postgres",
            marks=pytest.mark.skipif(
                not _database_available(),
                reason="no database reachable; run docker compose up -d",
            ),
        ),
    ]
)
def store(request):
    """Each test body runs once per store implementation."""
    impl = _sql_store() if request.param == "postgres" else InMemoryApprovalStore()
    impl.clear()
    yield impl
    impl.clear()


def _entry(what: str, decided_by: str = "HUMAN") -> AuditEntry:
    return AuditEntry(
        timestamp="2026-08-16T10:00:00+00:00", decided_by=decided_by, what=what, why="because"
    )


def test_unknown_invoice_returns_none(store):
    assert store.get(ORG, "INV-NOPE") is None


def test_records_and_reads_back_a_decision(store):
    store.record(
        ORG,
        "INV-1042",
        ApprovalRecord(
            state=ApprovalState.APPROVED,
            entries=[_entry("Approved ESCALATE")],
            recommended_action=RecommendedAction.ESCALATE,
            actor="tester",
        ),
    )

    record = store.get(ORG, "INV-1042")
    assert record is not None
    assert record.state is ApprovalState.APPROVED
    assert record.recommended_action is RecommendedAction.ESCALATE
    assert record.actor == "tester"
    assert [e.what for e in record.entries] == ["Approved ESCALATE"]


def test_audit_entries_keep_their_order(store):
    """FR-014 asks for the sequence, not just the latest state.

    Entries are written inside a single call and can share a timestamp to the
    microsecond, so ordering has to come from the stored sequence rather than
    from the clock.
    """
    entries = [_entry(f"step {i}", decided_by="AGENT") for i in range(6)]
    store.record(
        ORG,
        "INV-1042",
        ApprovalRecord(state=ApprovalState.APPROVED, entries=entries, actor="tester"),
    )

    record = store.get(ORG, "INV-1042")
    assert [e.what for e in record.entries] == [f"step {i}" for i in range(6)]


def test_second_decision_replaces_rather_than_duplicates(store):
    """An approve-then-reject keeps both facts, and neither is written twice."""
    first = [_entry("Approved FINANCE")]
    store.record(
        ORG,
        "INV-1038",
        ApprovalRecord(
            state=ApprovalState.APPROVED,
            entries=first,
            recommended_action=RecommendedAction.FINANCE,
            actor="first",
        ),
    )
    store.record(
        ORG,
        "INV-1038",
        ApprovalRecord(
            state=ApprovalState.REJECTED,
            entries=first + [_entry("Rejected FINANCE")],
            recommended_action=RecommendedAction.FINANCE,
            actor="second",
        ),
    )

    record = store.get(ORG, "INV-1038")
    assert record.state is ApprovalState.REJECTED
    assert [e.what for e in record.entries] == ["Approved FINANCE", "Rejected FINANCE"]
    assert record.actor == "second"


def test_orgs_cannot_see_each_others_decisions(store):
    """NFR-001 / BR-TENANT at the data-access layer, not per-endpoint."""
    store.record(
        ORG,
        "INV-1042",
        ApprovalRecord(state=ApprovalState.APPROVED, entries=[_entry("ours")], actor="a"),
    )

    assert store.get(OTHER_ORG, "INV-1042") is None
    assert store.get(ORG, "INV-1042") is not None


def test_clear_is_scoped_to_one_org(store):
    for org in (ORG, OTHER_ORG):
        store.record(
            org,
            "INV-1042",
            ApprovalRecord(state=ApprovalState.APPROVED, entries=[_entry("x")], actor="a"),
        )

    store.clear(ORG)

    assert store.get(ORG, "INV-1042") is None
    assert store.get(OTHER_ORG, "INV-1042") is not None


def test_returned_entries_are_a_copy(store):
    """Extending a recommendation's trail must not grow the stored history.

    `_apply_approval` calls `.extend()` on the recommendation it replays onto.
    If the store handed back its own list, every rebuild of the queue would
    append to the record and the trail would grow without bound.
    """
    store.record(
        ORG,
        "INV-1042",
        ApprovalRecord(state=ApprovalState.APPROVED, entries=[_entry("one")], actor="a"),
    )

    store.get(ORG, "INV-1042").entries.append(_entry("injected"))

    assert [e.what for e in store.get(ORG, "INV-1042").entries] == ["one"]


# --------------------------------------------------- degradation (#19)
#
# `audit_store=postgres` is a preference, not a demand: an unreachable database
# falls back to memory and keeps serving. These pin the part that makes that
# safe to live with — the fallback says so, loudly and observably.


def _unreachable_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "audit_store", "postgres")
    monkeypatch.setattr(
        settings, "database_url", "postgresql+psycopg://nobody@127.0.0.1:1/nothing"
    )


def test_an_unreachable_database_falls_back_instead_of_raising(monkeypatch):
    from app.decision_engine import store as store_module

    _unreachable_settings(monkeypatch)
    monkeypatch.setattr(
        store_module.SqlApprovalStore,
        "probe",
        lambda self: (_ for _ in ()).throw(OSError("connection refused")),
    )
    store_module.set_approval_store(None)

    assert isinstance(store_module.get_approval_store(), InMemoryApprovalStore)


def test_the_fallback_is_reported_rather_than_silent(monkeypatch, caplog):
    """The whole justification for degrading instead of failing."""
    from app.decision_engine import store as store_module

    _unreachable_settings(monkeypatch)
    monkeypatch.setattr(
        store_module.SqlApprovalStore,
        "probe",
        lambda self: (_ for _ in ()).throw(OSError("connection refused")),
    )
    store_module.set_approval_store(None)

    with caplog.at_level("WARNING"):
        store_module.get_approval_store()

    assert "will NOT survive a restart" in caplog.text

    status = store_module.audit_store_status()
    assert status.requested == "postgres"
    assert status.active == "memory"
    assert status.durable is False
    assert "connection refused" in status.degraded_reason


def test_a_degraded_process_still_records_decisions(monkeypatch):
    """Degraded means "not durable", not "not working"."""
    from app.decision_engine import store as store_module

    _unreachable_settings(monkeypatch)
    monkeypatch.setattr(
        store_module.SqlApprovalStore,
        "probe",
        lambda self: (_ for _ in ()).throw(OSError("connection refused")),
    )
    store_module.set_approval_store(None)

    store_module.get_approval_store().record(
        ORG,
        "INV-1042",
        ApprovalRecord(state=ApprovalState.APPROVED, entries=[_entry("x")], actor="a"),
    )

    assert store_module.get_approval_store().get(ORG, "INV-1042").state is ApprovalState.APPROVED


def test_memory_by_configuration_is_not_reported_as_degraded(monkeypatch):
    """Asking for memory and getting it is a choice, not a failure.

    Conflating the two would have /health permanently warning on the test and
    demo configurations, which is how a real warning gets ignored.
    """
    from app.config import settings
    from app.decision_engine import store as store_module

    monkeypatch.setattr(settings, "audit_store", "memory")
    store_module.set_approval_store(None)

    status = store_module.audit_store_status()
    assert status.active == "memory"
    assert status.durable is False
    assert status.degraded_reason is None


@pytest.mark.skipif(not _database_available(), reason="no database reachable")
def test_a_reachable_database_is_used_and_reported_durable(monkeypatch):
    from app.config import settings
    from app.decision_engine import store as store_module

    monkeypatch.setattr(settings, "audit_store", "postgres")
    store_module.set_approval_store(None)

    status = store_module.audit_store_status()
    assert status.active == "postgres"
    assert status.durable is True
    assert status.degraded_reason is None


@pytest.mark.skipif(not _database_available(), reason="no database reachable")
def test_an_unmigrated_database_degrades_rather_than_failing_later(monkeypatch):
    """A database that is up but missing the tables must not pass the probe.

    It would otherwise connect cleanly and fail on the first approval — exactly
    the late failure the fallback exists to prevent.
    """
    from sqlalchemy import text


    store = _sql_store()
    with store._session_factory() as session:
        session.execute(text("ALTER TABLE action_decisions RENAME TO action_decisions_tmp"))
        session.commit()
    try:
        with pytest.raises(Exception):  # noqa: B017 - any DB error must fail the probe
            store.probe()
    finally:
        with store._session_factory() as session:
            session.execute(
                text("ALTER TABLE action_decisions_tmp RENAME TO action_decisions")
            )
            session.commit()
