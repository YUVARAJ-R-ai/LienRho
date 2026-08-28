"""Turning Tally's XML into canonical types (#6, FR-001, NFR-006).

Nothing outside this module sees a Tally tag name. That is the whole point of
the canonical layer: the ML, rules, agent, and decision-engine code must not be
able to tell which accounting system the data came from.

Two things shape the code here.

**Tolerance about tag names.** ASM-01 has not been closed, so the exact
spellings a live TallyPrime returns are documented rather than observed. Field
lookups accept several documented spellings rather than one, because a single
guessed tag name that turns out wrong would produce a silent `None` and a
customer with no due date — which the rules engine would then treat as not yet
overdue. Being wrong loudly is recoverable; being wrong quietly is not.

**Refusing to guess amounts and dates.** A malformed amount raises rather than
defaulting to zero. Every statutory and financing decision downstream is
computed from these numbers (CON-05), and a zero that means "we could not read
it" is indistinguishable from a zero that means "nothing is owed".
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
)
from app.connectors.errors import ConnectorRejected
from app.connectors.tally.requests import TALLY_DATE_FORMAT


def parse_envelope(xml: str) -> ElementTree.Element:
    """Parse a response envelope, raising on a Tally-reported failure.

    Tally answers a rejected request with HTTP 200 and STATUS 0 in the body, so
    a caller that only checked the HTTP status would treat a refusal as an empty
    result set — an empty action queue that looks like "nothing to do today"
    rather than "we never got the data".
    """
    try:
        root = ElementTree.fromstring(xml.strip())
    except ElementTree.ParseError as exc:
        raise ConnectorRejected(f"TallyPrime returned XML that could not be parsed: {exc}") from exc

    status = _first_text(root, ["HEADER/STATUS", "STATUS"])
    if status is not None and status.strip() == "0":
        code = _first_text(root, ["BODY/DATA/STATUS.LIST/STATUS/CODE"])
        desc = _first_text(root, ["BODY/DATA/STATUS.LIST/STATUS/DESC"])
        raise ConnectorRejected(
            f"TallyPrime rejected the request: {desc or 'no reason given'}", code=code
        )

    return root


def parse_customers(xml: str, *, org_id: str) -> list[CanonicalCustomer]:
    root = parse_envelope(xml)
    customers = []

    for element in _collection_items(root, "LEDGER"):
        name = _attr_or_text(element, "NAME", ["NAME", "LEDGERNAME"])
        if not name:
            continue

        customers.append(
            CanonicalCustomer(
                org_id=org_id,
                # Tally has no customer id — the ledger name *is* the identity,
                # and it is what every voucher references.
                customer_id=name,
                customer_name=name,
                customer_type=_text(element, ["PARENT"]),
                # average_delay_days and relationship_duration_days are computed
                # from observed payment history in ml_core, never read from the
                # source. Copying a stored average in would reintroduce exactly
                # the label leakage ADR-004 exists to prevent.
            )
        )

    return customers


def parse_invoices(xml: str, *, org_id: str) -> list[CanonicalInvoice]:
    root = parse_envelope(xml)
    invoices = []

    for element in _collection_items(root, "BILLS", "BILL"):
        bill_ref = _attr_or_text(element, "NAME", ["NAME", "BILLREF"])
        customer = _text(element, ["PARENT", "LEDGERNAME", "PARTYLEDGERNAME"])
        bill_date = _date(element, ["BILLDATE", "DATE"])
        if not bill_ref or not customer or bill_date is None:
            continue

        # Tally signs a receivable's closing balance negative (it is a credit on
        # the party ledger). The canonical model wants what is owed, so take the
        # magnitude — and take it from closing, not opening, because opening is
        # the bill's original value before any part-payment.
        outstanding = abs(_amount(element, ["CLOSINGBALANCE", "AMOUNT"]) or Decimal(0))
        original = abs(_amount(element, ["OPENINGBALANCE"]) or outstanding)

        credit_days = _int(element, ["BILLCREDITPERIOD", "CREDITPERIOD"]) or 0

        if outstanding == 0:
            status = PaymentStatus.PAID
        elif original and outstanding < original:
            status = PaymentStatus.PARTIALLY_PAID
        else:
            status = PaymentStatus.PENDING

        invoices.append(
            CanonicalInvoice(
                org_id=org_id,
                invoice_id=bill_ref,
                customer_id=customer,
                invoice_amount=original,
                invoice_date=bill_date,
                due_date=_add_days(bill_date, credit_days),
                # Tally records no buyer acceptance — that is a TReDS/MSMED
                # concept, not an accounting one. Left None rather than
                # defaulted to the invoice date: check_msmed_threshold falls
                # back to the invoice date itself, and inventing an acceptance
                # here would make a guess look like a recorded fact.
                acceptance_date=None,
                payment_status=status,
            )
        )

    return invoices


def parse_payments(xml: str, *, org_id: str) -> list[CanonicalPayment]:
    """Receipt vouchers, one canonical payment per bill allocation.

    A single receipt often settles several bills, so the allocations are what
    map to payments — attributing the whole receipt to one invoice would corrupt
    the per-customer delay statistics the model trains on.
    """
    root = parse_envelope(xml)
    payments = []

    for voucher in _collection_items(root, "VOUCHER"):
        received_on = _date(voucher, ["DATE", "VOUCHERDATE"])
        party = _text(voucher, ["PARTYLEDGERNAME", "PARTYNAME", "LEDGERNAME"])
        if received_on is None or not party:
            continue

        allocations = voucher.findall(".//BILLALLOCATIONS.LIST") or voucher.findall(
            ".//BILLALLOCATIONS"
        )

        for allocation in allocations:
            bill_ref = _text(allocation, ["NAME", "BILLREF"])
            amount = _amount(allocation, ["AMOUNT"])
            if not bill_ref or amount is None:
                continue

            payments.append(
                CanonicalPayment(
                    org_id=org_id,
                    invoice_id=bill_ref,
                    customer_id=party,
                    # The bill's own due date is not on the receipt. It is filled
                    # in by the connector, which has the invoices to join against.
                    due_date=received_on,
                    actual_payment_date=received_on,
                    payment_amount=abs(amount),
                    payment_status=PaymentStatus.PAID,
                )
            )

    return payments


def parse_expenses(xml: str) -> list[dict]:
    root = parse_envelope(xml)
    expenses = []

    for element in _collection_items(root, "LEDGER"):
        name = _attr_or_text(element, "NAME", ["NAME", "LEDGERNAME"])
        amount = _amount(element, ["CLOSINGBALANCE"])
        if not name or amount is None:
            continue
        expenses.append({"name": name, "group": _text(element, ["PARENT"]), "amount": abs(amount)})

    return expenses


# --------------------------------------------------------------- helpers


def _collection_items(root: ElementTree.Element, *tags: str) -> list[ElementTree.Element]:
    """Every record in a collection response, whichever tag it arrived under.

    Tally wraps collection members in a tag named after the collection type, and
    pluralises inconsistently across types — hence accepting several.
    """
    items: list[ElementTree.Element] = []
    for tag in tags:
        items.extend(root.findall(f".//{tag}"))
        items.extend(root.findall(f".//{tag}.LIST"))
    return items


def _text(element: ElementTree.Element, names: list[str]) -> str | None:
    for name in names:
        found = element.find(name)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return None


def _attr_or_text(
    element: ElementTree.Element, attribute: str, names: list[str]
) -> str | None:
    """Tally puts a record's key in an attribute on some types and a child on others."""
    value = element.get(attribute)
    if value and value.strip():
        return value.strip()
    return _text(element, names)


def _first_text(root: ElementTree.Element, paths: list[str]) -> str | None:
    for path in paths:
        found = root.find(path)
        if found is not None and found.text:
            return found.text
    return None


def _amount(element: ElementTree.Element, names: list[str]) -> Decimal | None:
    raw = _text(element, names)
    if raw is None:
        return None
    # Tally emits amounts as plain signed decimals but can include a trailing
    # Dr/Cr marker depending on the field.
    cleaned = raw.replace(",", "").replace("Dr", "").replace("Cr", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ConnectorRejected(
            f"TallyPrime returned an amount that could not be read: {raw!r}"
        ) from exc


def _int(element: ElementTree.Element, names: list[str]) -> int | None:
    raw = _text(element, names)
    if raw is None:
        return None
    # Credit period arrives as "30 Days" as often as "30".
    digits = "".join(c for c in raw if c.isdigit())
    return int(digits) if digits else None


def _date(element: ElementTree.Element, names: list[str]) -> date | None:
    raw = _text(element, names)
    if raw is None:
        return None
    try:
        # No %z: Tally emits calendar dates with no time or zone, and an
        # invoice date is a calendar fact rather than an instant.
        return datetime.strptime(raw.strip(), TALLY_DATE_FORMAT).date()  # noqa: DTZ007
    except ValueError as exc:
        raise ConnectorRejected(
            f"TallyPrime returned a date that could not be read: {raw!r} "
            f"(expected {TALLY_DATE_FORMAT})"
        ) from exc


def _add_days(value: date, days: int) -> date:
    from datetime import timedelta

    return value + timedelta(days=days)


def join_payment_due_dates(
    payments: list[CanonicalPayment], invoices: list[CanonicalInvoice]
) -> list[CanonicalPayment]:
    """Fill each payment's due date and days_delayed from its bill, in place.

    A receipt voucher does not carry the bill's due date, and `days_delayed`
    is the single most important field the delay model trains on. Shared
    between `TallyConnector.get_payments` and `app.data.calibrate` so there is
    one join, not two that can quietly drift apart — the calibration report
    exists specifically to be trusted, so it can't run on a different
    definition of "delayed" than the model does.

    Returns the same list, mutated, for chaining convenience.
    """
    due_dates = {invoice.invoice_id: invoice.due_date for invoice in invoices}

    for payment in payments:
        due = due_dates.get(payment.invoice_id)
        if due is None:
            # Leave days_delayed None rather than computing it against the
            # placeholder due date the parser used. A fabricated zero would
            # enter the training set as an on-time payment.
            continue
        payment.due_date = due
        if payment.actual_payment_date is not None:
            payment.days_delayed = (payment.actual_payment_date - due).days

    return payments
