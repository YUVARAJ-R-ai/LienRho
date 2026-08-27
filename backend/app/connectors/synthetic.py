"""The demo dataset, behind the connector interface (FR-001, NFR-006).

The synthetic portfolio was reachable only through `generate_dataset()`, which
meant the sync path had to special-case it and the connector interface had
exactly one real implementation. Wrapping it here does two things:

- the sync path takes an `AccountingConnector` and never asks which one, so the
  whole ingest → normalize → persist loop is exercised by the demo data rather
  than only by a Tally instance nobody has;
- it is NFR-006's acceptance criterion, run for real — "a canned-data test
  connector integrates with 0 changes required outside the connector module and
  its registration point". This module and the registry entry are the only
  things that were added.

It holds no state and re-derives the dataset per call. `generate_dataset` is
deterministic for a given seed, so two calls return the same portfolio; that is
what makes a re-run sync idempotent (FR-001 AC-3) rather than a source of drift.
"""

from __future__ import annotations

from datetime import date

from app.canonical.models import CanonicalCustomer, CanonicalInvoice, CanonicalPayment
from app.connectors.base import AccountingConnector
from app.connectors.errors import ConnectorUnsupported
from app.data.synthetic import AS_OF, DEFAULT_SEED, generate_dataset


class SyntheticConnector(AccountingConnector):
    """Serves the generated demo portfolio as if it came from an accounting system."""

    def __init__(self, *, seed: int = DEFAULT_SEED, as_of: date = AS_OF) -> None:
        self._seed = seed
        self._as_of = as_of

    def _dataset(self, org_id: str):
        return generate_dataset(seed=self._seed, org_id=org_id, as_of=self._as_of)

    def get_customers(self, org_id: str) -> list[CanonicalCustomer]:
        return self._dataset(org_id).customers

    def get_invoices(self, org_id: str) -> list[CanonicalInvoice]:
        return self._dataset(org_id).invoices

    def get_payments(self, org_id: str) -> list[CanonicalPayment]:
        return self._dataset(org_id).payments

    def get_expenses(self, org_id: str) -> list[dict]:
        # The demo's expense figures are business-state constants in
        # decision_engine/service.py, not per-ledger rows, so there is nothing
        # honest to return here. Empty rather than invented.
        return []

    def create_task(self, org_id: str, description: str) -> None:
        raise ConnectorUnsupported("The synthetic connector does not accept writes.")
