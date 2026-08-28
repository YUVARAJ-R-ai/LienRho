"""Strip real customer identity out of canonical records before they leave a
person's machine (CP4 — calibrating the synthetic model against real invoice
history, per ADR-004's "no free lunch on labels" discipline extended to PII).

The one fact that shapes everything here: the Tally connector's parser sets
`customer_id = <ledger name>` (see `connectors/tally/parser.py`). The ledger
name **is** the customer's real business name. Hashing `customer_name` and
leaving `customer_id` alone — the obvious first instinct — would leave the
real name sitting in every invoice, payment, and customer record anyway,
since that field IS the name. Everything below therefore remaps
`customer_id` itself, consistently across all three collections, and drops
`customer_name` entirely rather than assuming the two are independent.

This only ever needs to produce a dataset good enough to compare *aggregate*
statistics (delay distributions, late rates) against the synthetic generator's
assumptions. It has no obligation to preserve anything about who a customer
is, and deliberately doesn't.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from app.canonical.models import CanonicalCustomer, CanonicalInvoice, CanonicalPayment


@dataclass
class Pseudonymizer:
    """Maps real customer_ids to pseudonyms, consistently within one run.

    The salt is generated fresh per instance and never exposed or written
    anywhere — there is no `salt` property, no `__repr__` that could leak it,
    and no way to reconstruct it from the output. That's deliberate: the
    default posture is "these pseudonyms cannot be reversed by anyone,
    including the person who ran this," rather than "cannot be reversed by
    someone without the salt." A calibration report has no need for
    pseudonyms to survive across separate runs, so there's nothing to trade
    away by making them one-shot.

    If cross-run stability is ever genuinely needed (e.g. tracking the same
    anonymized customer across two exports taken weeks apart), pass an
    explicit `salt` — but that moves the security property from "can't be
    reversed" to "can't be reversed without the salt," which is a real
    downgrade and should be a deliberate choice, not a default.
    """

    _salt: bytes = field(default_factory=lambda: os.urandom(32), repr=False)
    _cache: dict[str, str] = field(default_factory=dict)

    def pseudonym_for(self, real_id: str) -> str:
        if real_id not in self._cache:
            digest = hashlib.sha256(self._salt + real_id.encode("utf-8")).hexdigest()
            self._cache[real_id] = f"CUST-{digest[:10].upper()}"
        return self._cache[real_id]

    @property
    def customer_count(self) -> int:
        """How many distinct real customers were seen — safe to report, unlike the mapping."""
        return len(self._cache)


def sanitize_customer(customer: CanonicalCustomer, pseudonymizer: Pseudonymizer) -> CanonicalCustomer:
    pseudonym = pseudonymizer.pseudonym_for(customer.customer_id)
    return customer.model_copy(
        update={
            "customer_id": pseudonym,
            # Real business name dropped, not hashed-and-kept — a hash of a
            # short, guessable business name is not meaningfully anonymous
            # (a dictionary/rainbow attack over a supplier's known customer
            # list would defeat it in seconds). The placeholder carries no
            # information the pseudonym doesn't already carry.
            "customer_name": pseudonym,
        }
    )


def sanitize_invoice(invoice: CanonicalInvoice, pseudonymizer: Pseudonymizer) -> CanonicalInvoice:
    return invoice.model_copy(
        update={"customer_id": pseudonymizer.pseudonym_for(invoice.customer_id)}
    )


def sanitize_payment(payment: CanonicalPayment, pseudonymizer: Pseudonymizer) -> CanonicalPayment:
    return payment.model_copy(
        update={"customer_id": pseudonymizer.pseudonym_for(payment.customer_id)}
    )


@dataclass
class SanitizedPortfolio:
    customers: list[CanonicalCustomer]
    invoices: list[CanonicalInvoice]
    payments: list[CanonicalPayment]
    # Not the mapping — just a count, safe to log/print.
    customers_pseudonymized: int


def sanitize_portfolio(
    *,
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
) -> SanitizedPortfolio:
    """Sanitize a full portfolio with one consistent id mapping.

    One `Pseudonymizer` shared across all three collections is the whole
    point: a customer who appears in `payments` but was missed by a
    `customers.xml` export (a real possibility — exports can be partial)
    still gets the same pseudonym as everywhere else they show up, because
    the mapping is built lazily from whatever `customer_id` it's asked about
    first, not from the customers list alone.
    """
    pseudonymizer = Pseudonymizer()

    sanitized_customers = [sanitize_customer(c, pseudonymizer) for c in customers]
    sanitized_invoices = [sanitize_invoice(i, pseudonymizer) for i in invoices]
    sanitized_payments = [sanitize_payment(p, pseudonymizer) for p in payments]

    return SanitizedPortfolio(
        customers=sanitized_customers,
        invoices=sanitized_invoices,
        payments=sanitized_payments,
        customers_pseudonymized=pseudonymizer.customer_count,
    )
