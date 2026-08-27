"""Connector → canonical store (FR-001).

The canonical tables existed and nothing ever wrote to them: the portfolio was
rebuilt from the connector on every request and thrown away. That left FR-001's
acceptance criteria unmeetable — there was no store to populate, no run to fail,
and nothing that could be duplicated by a re-run.

Each criterion maps to a specific decision here:

**AC-1 — every invoice populated in the canonical store.** `sync_portfolio`
writes customers, invoices, and payments, and the API can then read the store
instead of the connector.

**AC-2 — a failed sync reports itself and does not overwrite good data with
partial results.** The entire read happens *before* any write, and the writes
share one transaction. A connector that dies halfway leaves the previous
portfolio exactly as it was, and a FAILED `SyncRun` row saying when and why.
The alternative — streaming rows in as they arrive — turns a network blip into
a half-erased book, which is worse than not syncing at all.

**AC-3 — a re-run creates no duplicates.** Customers and invoices upsert on
their natural keys. Payments have no natural key in the canonical model, so
they are replaced wholesale for the org inside the same transaction; see
`_replace_payments`.

Everything is scoped by `org_id` (NFR-001): a sync writes into one tenant and
reads back only that tenant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
)
from app.connectors.base import AccountingConnector
from app.data.synthetic import GeneratedDataset
from app.db.models import Customer, Invoice, Payment, SyncRun

logger = logging.getLogger(__name__)


class SyncFailed(Exception):
    """The connector read failed; nothing was written."""


@dataclass(frozen=True)
class SyncResult:
    """What one sync did, mirroring the SyncRun row it wrote."""

    org_id: str
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    customers_synced: int = 0
    invoices_synced: int = 0
    payments_synced: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCESS"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sync_portfolio(
    session: Session, *, org_id: str, connector: AccountingConnector, source: str
) -> SyncResult:
    """Read one org's book from `connector` and write it to the canonical store.

    Returns a SyncResult either way — a failed sync is a fact to be recorded,
    not an exception for the caller to decide about. The `SyncRun` row is
    committed on its own so it survives the rollback of a failed data write.
    """
    started = _now()

    # Read everything first. Nothing below this block touches the database, so
    # a connector failure here cannot leave a partial portfolio (AC-2).
    try:
        customers = connector.get_customers(org_id)
        invoices = connector.get_invoices(org_id)
        payments = connector.get_payments(org_id)
    except Exception as exc:  # noqa: BLE001 - every connector failure is recorded alike
        logger.warning("sync from %s failed for %s: %s", source, org_id, exc)
        return _record_run(
            session,
            SyncResult(
                org_id=org_id,
                source=source,
                status="FAILED",
                started_at=started,
                finished_at=_now(),
                error=f"{type(exc).__name__}: {exc}",
            ),
        )

    try:
        _upsert_customers(session, org_id=org_id, customers=customers)
        _upsert_invoices(session, org_id=org_id, invoices=invoices)
        _replace_payments(session, org_id=org_id, payments=payments)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - a write failure must not half-apply
        session.rollback()
        logger.warning("sync write failed for %s: %s", org_id, exc)
        return _record_run(
            session,
            SyncResult(
                org_id=org_id,
                source=source,
                status="FAILED",
                started_at=started,
                finished_at=_now(),
                error=f"{type(exc).__name__}: {exc}",
            ),
        )

    return _record_run(
        session,
        SyncResult(
            org_id=org_id,
            source=source,
            status="SUCCESS",
            started_at=started,
            finished_at=_now(),
            customers_synced=len(customers),
            invoices_synced=len(invoices),
            payments_synced=len(payments),
        ),
    )


def last_sync(session: Session, *, org_id: str) -> SyncResult | None:
    """The most recent run for this org, successful or not (FR-001 AC-2)."""
    row = session.execute(
        select(SyncRun)
        .where(SyncRun.org_id == org_id)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _to_result(row) if row is not None else None


def load_portfolio(session: Session, *, org_id: str) -> GeneratedDataset:
    """Read one org's portfolio back out of the canonical store.

    Returns the same container the synthetic path returns, so the decision
    engine cannot tell whether it is looking at generated data, a Tally sync, or
    a database read.
    """
    customers = [
        CanonicalCustomer(
            org_id=row.org_id,
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            industry=row.industry,
            customer_type=row.customer_type,
            average_delay_days=row.average_delay_days,
            relationship_duration_days=row.relationship_duration_days,
            treds_status=row.treds_status,
        )
        for row in session.execute(
            select(Customer).where(Customer.org_id == org_id).order_by(Customer.customer_id)
        ).scalars()
    ]

    invoices = [
        CanonicalInvoice(
            org_id=row.org_id,
            invoice_id=row.invoice_id,
            customer_id=row.customer_id,
            invoice_amount=row.invoice_amount,
            invoice_date=row.invoice_date,
            due_date=row.due_date,
            acceptance_date=row.acceptance_date,
            payment_status=PaymentStatus(row.payment_status),
            payment_date=row.payment_date,
        )
        for row in session.execute(
            select(Invoice).where(Invoice.org_id == org_id).order_by(Invoice.invoice_id)
        ).scalars()
    ]

    payments = [
        CanonicalPayment(
            org_id=row.org_id,
            invoice_id=row.invoice_id,
            customer_id=row.customer_id,
            due_date=row.due_date,
            actual_payment_date=row.actual_payment_date,
            days_delayed=row.days_delayed,
            payment_amount=row.payment_amount,
            payment_status=PaymentStatus(row.payment_status),
        )
        for row in session.execute(
            select(Payment).where(Payment.org_id == org_id).order_by(Payment.id)
        ).scalars()
    ]

    return GeneratedDataset(customers=customers, invoices=invoices, payments=payments)


# --------------------------------------------------------------- writes


def _upsert_customers(
    session: Session, *, org_id: str, customers: list[CanonicalCustomer]
) -> None:
    """Insert or update by customer_id (AC-3: a re-run adds no duplicates)."""
    existing = {
        row.customer_id: row
        for row in session.execute(
            select(Customer).where(Customer.org_id == org_id)
        ).scalars()
    }

    for customer in customers:
        row = existing.get(customer.customer_id)
        if row is None:
            session.add(Customer(**customer.model_dump()))
            continue
        for field, value in customer.model_dump().items():
            setattr(row, field, value)


def _upsert_invoices(session: Session, *, org_id: str, invoices: list[CanonicalInvoice]) -> None:
    """Insert or update by invoice_id.

    Updating rather than replacing matters: an invoice that has been paid since
    the last sync must change status in place, not disappear and come back with
    the derived state that referenced it dangling.
    """
    existing = {
        row.invoice_id: row
        for row in session.execute(
            select(Invoice).where(Invoice.org_id == org_id)
        ).scalars()
    }

    for invoice in invoices:
        payload = invoice.model_dump()
        payload["payment_status"] = invoice.payment_status.value
        row = existing.get(invoice.invoice_id)
        if row is None:
            session.add(Invoice(**payload))
            continue
        for field, value in payload.items():
            setattr(row, field, value)


def _replace_payments(session: Session, *, org_id: str, payments: list[CanonicalPayment]) -> None:
    """Replace this org's payment history wholesale.

    Payments carry a surrogate id and no natural key — the canonical model has
    no field, or combination of them, guaranteed unique for a customer who
    settles two bills for the same amount on the same day. Upserting would
    therefore either duplicate those rows on every sync or silently merge two
    genuine payments into one.

    Deleting and reinserting inside the caller's transaction avoids both, and
    is safe for the same reason the read happens first: nothing is committed
    unless the whole write succeeds. Payment history is connector-owned
    reference data — LIENRHO derives from it but never edits it — so nothing is
    lost by rewriting it.
    """
    session.execute(delete(Payment).where(Payment.org_id == org_id))
    for payment in payments:
        payload = payment.model_dump()
        payload["payment_status"] = payment.payment_status.value
        session.add(Payment(**payload))


def _record_run(session: Session, result: SyncResult) -> SyncResult:
    """Persist the run and commit it separately from the data write.

    Its own commit on purpose: a failed sync rolls the data write back, and the
    record of that failure must not be rolled back with it.
    """
    session.add(
        SyncRun(
            org_id=result.org_id,
            source=result.source,
            status=result.status,
            started_at=result.started_at,
            finished_at=result.finished_at,
            customers_synced=result.customers_synced,
            invoices_synced=result.invoices_synced,
            payments_synced=result.payments_synced,
            error=result.error,
        )
    )
    session.commit()
    return result


def _to_result(row: SyncRun) -> SyncResult:
    return SyncResult(
        org_id=row.org_id,
        source=row.source,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        customers_synced=row.customers_synced,
        invoices_synced=row.invoices_synced,
        payments_synced=row.payments_synced,
        error=row.error,
    )
