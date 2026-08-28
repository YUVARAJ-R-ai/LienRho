from datetime import date
from decimal import Decimal
from pathlib import Path

from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
)
from app.connectors.tally import parser
from app.data.sanitize import Pseudonymizer, sanitize_portfolio

FIXTURES = Path(__file__).parent / "fixtures" / "tally"


def _customer(customer_id="ABC Logistics Pvt Ltd", name="ABC Logistics Pvt Ltd"):
    return CanonicalCustomer(org_id="ORG-TEST", customer_id=customer_id, customer_name=name)


def _invoice(customer_id="ABC Logistics Pvt Ltd"):
    return CanonicalInvoice(
        org_id="ORG-TEST",
        invoice_id="INV-1",
        customer_id=customer_id,
        invoice_amount=Decimal(100000),
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 2, 1),
        payment_status=PaymentStatus.PAID,
    )


def _payment(customer_id="ABC Logistics Pvt Ltd"):
    return CanonicalPayment(
        org_id="ORG-TEST",
        invoice_id="INV-1",
        customer_id=customer_id,
        due_date=date(2026, 2, 1),
        actual_payment_date=date(2026, 2, 10),
        days_delayed=9,
        payment_amount=Decimal(100000),
        payment_status=PaymentStatus.PAID,
    )


# ------------------------------------------------------------- Pseudonymizer


def test_same_real_id_always_maps_to_the_same_pseudonym():
    p = Pseudonymizer()
    assert p.pseudonym_for("Apex Trading") == p.pseudonym_for("Apex Trading")


def test_different_real_ids_map_to_different_pseudonyms():
    p = Pseudonymizer()
    assert p.pseudonym_for("Apex Trading") != p.pseudonym_for("ABC Logistics")


def test_two_instances_produce_different_pseudonyms_for_the_same_name():
    """The core privacy property: no fixed mapping exists across runs.

    Different random salts per instance mean the same real customer gets a
    different pseudonym each run, so two exports can't be cross-referenced by
    comparing pseudonyms.
    """
    a = Pseudonymizer().pseudonym_for("Apex Trading")
    b = Pseudonymizer().pseudonym_for("Apex Trading")
    assert a != b


def test_pseudonym_never_contains_the_real_name():
    pseudonym = Pseudonymizer().pseudonym_for("Apex Trading Private Limited")
    assert "apex" not in pseudonym.lower()
    assert "trading" not in pseudonym.lower()


def test_customer_count_reports_distinct_customers_only():
    p = Pseudonymizer()
    p.pseudonym_for("A")
    p.pseudonym_for("B")
    p.pseudonym_for("A")  # repeat
    assert p.customer_count == 2


# --------------------------------------------------------- sanitize_portfolio


def test_real_name_does_not_survive_sanitization():
    result = sanitize_portfolio(
        customers=[_customer()], invoices=[_invoice()], payments=[_payment()]
    )
    blob = " ".join(
        [c.customer_name + c.customer_id for c in result.customers]
        + [i.customer_id for i in result.invoices]
        + [p.customer_id for p in result.payments]
    )
    assert "ABC" not in blob
    assert "Logistics" not in blob


def test_same_customer_gets_one_consistent_pseudonym_across_all_three_collections():
    result = sanitize_portfolio(
        customers=[_customer()], invoices=[_invoice()], payments=[_payment()]
    )
    ids = {result.customers[0].customer_id, result.invoices[0].customer_id, result.payments[0].customer_id}
    assert len(ids) == 1


def test_customer_missing_from_the_ledger_export_still_gets_pseudonymized():
    """A customer can appear in payments/invoices without a matching LEDGER
    entry (partial exports happen). The mapping must still be consistent."""
    result = sanitize_portfolio(
        customers=[],  # no customers.xml equivalent for this one
        invoices=[_invoice(customer_id="Ghost Customer")],
        payments=[_payment(customer_id="Ghost Customer")],
    )
    assert result.invoices[0].customer_id == result.payments[0].customer_id
    assert result.customers_pseudonymized == 1


def test_numeric_fields_are_untouched_by_sanitization():
    """Sanitizing must not corrupt the statistics calibration depends on."""
    invoice = _invoice()
    payment = _payment()
    result = sanitize_portfolio(customers=[], invoices=[invoice], payments=[payment])

    assert result.invoices[0].invoice_amount == invoice.invoice_amount
    assert result.invoices[0].due_date == invoice.due_date
    assert result.payments[0].days_delayed == payment.days_delayed
    assert result.payments[0].payment_amount == payment.payment_amount


def test_pseudonymized_output_is_valid_json_serializable():
    """The whole point is a report safe to write to disk or paste into a slide."""
    import json

    result = sanitize_portfolio(customers=[_customer()], invoices=[_invoice()], payments=[_payment()])
    json.dumps(
        [c.model_dump(mode="json") for c in result.customers]
        + [i.model_dump(mode="json") for i in result.invoices]
        + [p.model_dump(mode="json") for p in result.payments]
    )


# --------------------------------------------- end-to-end against real fixtures


def test_end_to_end_against_the_tally_fixtures_leaks_no_real_name():
    """Parses the same fixtures the connector's own tests use, then sanitizes.

    This is what stands in for "run against real data" until real data
    exists: it proves the parse -> sanitize pipeline holds together on
    Tally's actual XML shape, not a hand-built canonical object.
    """
    customers = parser.parse_customers(
        (FIXTURES / "customers.xml").read_text(), org_id="ORG-TEST"
    )
    invoices = parser.parse_invoices(
        (FIXTURES / "invoices.xml").read_text(), org_id="ORG-TEST"
    )
    payments = parser.parse_payments(
        (FIXTURES / "payments.xml").read_text(), org_id="ORG-TEST"
    )

    result = sanitize_portfolio(customers=customers, invoices=invoices, payments=payments)

    blob = " ".join(
        c.customer_name + c.customer_id for c in result.customers
    ) + " ".join(i.customer_id for i in result.invoices)

    # Real names present in the fixtures — none may survive.
    for real_name in ("ABC Logistics", "Global Retail"):
        assert real_name not in blob

    assert result.customers_pseudonymized >= 2
