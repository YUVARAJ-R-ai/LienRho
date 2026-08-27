"""Connector sync into the canonical store (FR-001).

Structured around FR-001's three acceptance criteria, because those are what
the requirement is judged on and each one is a specific claim about behaviour
under failure or repetition rather than about the happy path.

Needs a database — the whole point is persistence — so the module skips when
none is reachable, the same way `test_approval_store.py` does.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
)
from app.config import settings
from app.connectors.base import AccountingConnector
from app.connectors.synthetic import SyntheticConnector
from app.db.models import Customer, Invoice, Payment, SyncRun
from app.sync import last_sync, load_portfolio, sync_portfolio

ORG = "ORG-SYNC-TEST"
OTHER_ORG = "ORG-SYNC-OTHER"


def _database_available() -> bool:
    try:
        with create_engine(settings.database_url).connect():
            return True
    except Exception:  # noqa: BLE001 - any failure to connect means "skip"
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="sync is about persistence; needs a database"
)


@pytest.fixture
def session():
    factory = sessionmaker(bind=create_engine(settings.database_url), autoflush=False)
    with factory() as s:
        _wipe(s)
        yield s
        _wipe(s)


def _wipe(session) -> None:
    for org in (ORG, OTHER_ORG):
        for model in (Payment, Invoice, Customer, SyncRun):
            session.execute(delete(model).where(model.org_id == org))
    session.commit()


class FakeConnector(AccountingConnector):
    """A connector whose contents and failure mode the test controls."""

    def __init__(self, *, customers=None, invoices=None, payments=None, fail_on=None):
        self._customers = customers or []
        self._invoices = invoices or []
        self._payments = payments or []
        self._fail_on = fail_on

    def _maybe_fail(self, which: str):
        if self._fail_on == which:
            raise ConnectionError(f"tally unreachable while reading {which}")

    def get_customers(self, org_id):
        self._maybe_fail("customers")
        return [c.model_copy(update={"org_id": org_id}) for c in self._customers]

    def get_invoices(self, org_id):
        self._maybe_fail("invoices")
        return [i.model_copy(update={"org_id": org_id}) for i in self._invoices]

    def get_payments(self, org_id):
        self._maybe_fail("payments")
        return [p.model_copy(update={"org_id": org_id}) for p in self._payments]

    def get_expenses(self, org_id):
        return []

    def create_task(self, org_id, description):
        raise NotImplementedError


def customer(cid="CUST-1", name="ABC Logistics") -> CanonicalCustomer:
    return CanonicalCustomer(org_id=ORG, customer_id=cid, customer_name=name)


def invoice(iid="INV-1", amount="100000", status=PaymentStatus.PENDING) -> CanonicalInvoice:
    return CanonicalInvoice(
        org_id=ORG,
        invoice_id=iid,
        customer_id="CUST-1",
        invoice_amount=Decimal(amount),
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 7, 1),
        payment_status=status,
    )


def payment(iid="INV-1", amount="50000") -> CanonicalPayment:
    return CanonicalPayment(
        org_id=ORG,
        invoice_id=iid,
        customer_id="CUST-1",
        due_date=date(2026, 7, 1),
        actual_payment_date=date(2026, 7, 10),
        days_delayed=9,
        payment_amount=Decimal(amount),
        payment_status=PaymentStatus.PAID,
    )


def _sync(session, connector, org_id=ORG):
    return sync_portfolio(session, org_id=org_id, connector=connector, source="synthetic")


# ------------------------------------------------- AC-1: the store is populated


def test_sync_populates_the_canonical_store(session):
    """FR-001 AC-1: every invoice has its canonical fields in the store."""
    result = _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]))

    assert result.succeeded
    assert result.invoices_synced == 1

    stored = load_portfolio(session, org_id=ORG)
    assert [i.invoice_id for i in stored.invoices] == ["INV-1"]
    row = stored.invoices[0]
    assert all(
        v is not None
        for v in (
            row.invoice_id,
            row.customer_id,
            row.invoice_amount,
            row.invoice_date,
            row.due_date,
            row.payment_status,
        )
    )


def test_the_synthetic_connector_round_trips_the_whole_demo_portfolio(session):
    """NFR-006's acceptance criterion, run for real.

    A canned-data connector integrates with no changes outside its own module,
    and the full demo portfolio survives the trip through the store.
    """
    result = _sync(session, SyntheticConnector())

    assert result.succeeded
    assert result.invoices_synced == 30

    stored = load_portfolio(session, org_id=ORG)
    assert len(stored.invoices) == 30
    assert len(stored.customers) > 0
    assert len(stored.payments) > 0


def test_decimal_and_date_fidelity_survives_the_round_trip(session):
    """An amount that changes on the way through the store corrupts every
    statutory figure computed from it (CON-05)."""
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice(amount="412345.67")]))

    stored = load_portfolio(session, org_id=ORG).invoices[0]
    assert stored.invoice_amount == Decimal("412345.67")
    assert stored.invoice_date == date(2026, 6, 1)
    assert stored.due_date == date(2026, 7, 1)


# --------------------------------------- AC-2: failures reported, data intact


def test_a_failed_sync_leaves_the_previous_portfolio_intact(session):
    """FR-001 AC-2, the part that matters most.

    A connector dying mid-read must not half-erase a book that was fine. The
    read completes before any write for exactly this reason.
    """
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]))

    result = _sync(session, FakeConnector(customers=[customer()], fail_on="invoices"))

    assert not result.succeeded
    assert "unreachable" in result.error

    stored = load_portfolio(session, org_id=ORG)
    assert [i.invoice_id for i in stored.invoices] == ["INV-1"]


def test_a_failed_sync_is_recorded_with_a_timestamp(session):
    """Otherwise "empty queue" and "never read the book" look identical."""
    _sync(session, FakeConnector(fail_on="customers"))

    recorded = last_sync(session, org_id=ORG)
    assert recorded.status == "FAILED"
    assert recorded.started_at is not None
    assert recorded.finished_at is not None
    assert "unreachable" in recorded.error


def test_the_failure_record_survives_the_rollback_of_the_data_write(session):
    """The run row is committed separately on purpose.

    Sharing the data write's transaction would roll the evidence of the failure
    back along with the failure.
    """
    _sync(session, FakeConnector(fail_on="payments"))

    assert session.query(SyncRun).filter(SyncRun.org_id == ORG).count() == 1


def test_a_later_success_does_not_erase_the_earlier_failure(session):
    """A run failing since Tuesday should read as a pattern, not one stale row."""
    _sync(session, FakeConnector(fail_on="customers"))
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]))

    assert session.query(SyncRun).filter(SyncRun.org_id == ORG).count() == 2
    assert last_sync(session, org_id=ORG).status == "SUCCESS"


# ------------------------------------------------- AC-3: re-runs don't duplicate


def test_a_re_run_with_no_changes_creates_no_duplicates(session):
    """FR-001 AC-3, stated verbatim in the requirement."""
    connector = FakeConnector(
        customers=[customer()], invoices=[invoice()], payments=[payment()]
    )
    for _ in range(3):
        _sync(session, connector)

    stored = load_portfolio(session, org_id=ORG)
    assert len(stored.invoices) == 1
    assert len(stored.customers) == 1
    assert len(stored.payments) == 1


def test_the_full_demo_portfolio_is_idempotent_across_re_runs(session):
    """30 invoices, twice, still 30 — the realistic version of AC-3."""
    for _ in range(2):
        _sync(session, SyntheticConnector())

    assert len(load_portfolio(session, org_id=ORG).invoices) == 30


def test_a_changed_invoice_updates_in_place(session):
    """An invoice paid since the last sync changes status; it is not re-added."""
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]))
    _sync(
        session,
        FakeConnector(
            customers=[customer()], invoices=[invoice(status=PaymentStatus.PAID)]
        ),
    )

    stored = load_portfolio(session, org_id=ORG)
    assert len(stored.invoices) == 1
    assert stored.invoices[0].payment_status is PaymentStatus.PAID


def test_payments_do_not_accumulate_across_syncs(session):
    """Payments have no natural key, so they are replaced wholesale.

    Upserting them would either duplicate on every run or silently merge two
    genuine same-day, same-amount payments into one.
    """
    connector = FakeConnector(
        customers=[customer()],
        invoices=[invoice()],
        # Two genuinely distinct payments that are identical in every field.
        payments=[payment(), payment()],
    )
    _sync(session, connector)
    _sync(session, connector)

    assert len(load_portfolio(session, org_id=ORG).payments) == 2


# --------------------------------------------------------------- NFR-001


def test_a_sync_writes_into_only_its_own_org(session):
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]), org_id=ORG)
    _sync(
        session,
        FakeConnector(customers=[customer()], invoices=[invoice(iid="INV-OTHER")]),
        org_id=OTHER_ORG,
    )

    assert [i.invoice_id for i in load_portfolio(session, org_id=ORG).invoices] == ["INV-1"]
    assert [i.invoice_id for i in load_portfolio(session, org_id=OTHER_ORG).invoices] == [
        "INV-OTHER"
    ]


def test_one_orgs_failed_sync_does_not_touch_another(session):
    _sync(session, FakeConnector(customers=[customer()], invoices=[invoice()]), org_id=ORG)
    _sync(session, FakeConnector(fail_on="customers"), org_id=OTHER_ORG)

    assert len(load_portfolio(session, org_id=ORG).invoices) == 1
    assert last_sync(session, org_id=ORG).status == "SUCCESS"
    assert last_sync(session, org_id=OTHER_ORG).status == "FAILED"


def test_last_sync_is_none_before_anything_has_run(session):
    assert last_sync(session, org_id=ORG) is None


def test_an_empty_store_reads_as_an_empty_portfolio(session):
    stored = load_portfolio(session, org_id=ORG)
    assert stored.invoices == []
    assert stored.customers == []
