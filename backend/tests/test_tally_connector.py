"""TallyConnector (FR-001, CON-02, NFR-006, #6).

These run against recorded fixtures of Tally's documented XML format, not a
live instance — ASM-01 is still open. So they prove the envelope construction,
the failure handling, and the canonical mapping, and they do not prove that a
real TallyPrime answers this way. The tests worth most here are the refusals:
a rejected request that must not look like an empty book, and an unreadable
amount that must not become a zero.
"""

from __future__ import annotations

import pathlib
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

import pytest

from app.canonical.models import PaymentStatus
from app.connectors.base import AccountingConnector
from app.connectors.errors import ConnectorRejected, ConnectorUnsupported
from app.connectors.tally import TallyConfig, TallyConnector, parser, requests
from app.connectors.tally.transport import RecordedTallyTransport

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "tally"
ORG = "ORG-DEMO"
AS_OF = date(2026, 8, 16)


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.xml").read_text()


def connector(*responses: str, as_of: date = AS_OF) -> tuple[TallyConnector, RecordedTallyTransport]:
    transport = RecordedTallyTransport([fixture(name) for name in responses])
    return (
        TallyConnector(
            TallyConfig(company="Demo Supplier Pvt Ltd"), transport=transport, as_of=as_of
        ),
        transport,
    )


# --------------------------------------------------------------- interface


def test_implements_the_connector_interface():
    """NFR-006: a new connector implements this and nothing else changes."""
    assert issubclass(TallyConnector, AccountingConnector)


def test_create_task_refuses_rather_than_silently_doing_nothing():
    """Tally has no task entity.

    Returning None would let a caller believe it recorded a follow-up that
    was never recorded anywhere.
    """
    tally, _ = connector()
    with pytest.raises(ConnectorUnsupported):
        tally.create_task(ORG, "Chase INV-1023")


# --------------------------------------------------------------- failures


def test_a_rejected_request_raises_instead_of_returning_nothing():
    """The most dangerous failure mode this connector has.

    Tally answers a rejected request with HTTP 200 and STATUS 0. A caller that
    only checked the HTTP status would read a refusal as an empty collection —
    an empty action queue that reads as "nothing to do today" rather than "we
    never got the data".
    """
    tally, _ = connector("rejected")
    with pytest.raises(ConnectorRejected) as exc:
        tally.get_customers(ORG)

    assert "Could not find the specified company" in str(exc.value)
    assert exc.value.code == "-1"


def test_unparseable_xml_is_reported_as_a_rejection():
    tally = TallyConnector(
        TallyConfig(company="X"), transport=RecordedTallyTransport(["not xml at all"])
    )
    with pytest.raises(ConnectorRejected):
        tally.get_customers(ORG)


def test_an_unreadable_amount_raises_rather_than_becoming_zero():
    """CON-05: every statutory and financing figure is computed from these.

    A zero meaning "could not read" is indistinguishable from a zero meaning
    "nothing is owed", and the second one silently clears a statutory breach.
    """
    broken = fixture("invoices").replace("-412000.00", "four lakh twelve thousand")
    with pytest.raises(ConnectorRejected):
        parser.parse_invoices(broken, org_id=ORG)


def test_an_unreadable_date_raises_rather_than_being_skipped():
    broken = fixture("invoices").replace("20260601", "01-06-2026")
    with pytest.raises(ConnectorRejected):
        parser.parse_invoices(broken, org_id=ORG)


# --------------------------------------------------------------- customers


def test_customers_map_to_canonical():
    tally, _ = connector("customers")
    customers = tally.get_customers(ORG)

    assert [c.customer_name for c in customers] == [
        "ABC Logistics Pvt Ltd",
        "Global Retail Ltd",
    ]
    assert all(c.org_id == ORG for c in customers)


def test_customer_id_is_the_ledger_name():
    """Tally has no customer id — the ledger name is what vouchers reference."""
    tally, _ = connector("customers")
    assert tally.get_customers(ORG)[0].customer_id == "ABC Logistics Pvt Ltd"


def test_customer_delay_statistics_are_not_read_from_the_source():
    """ADR-004: any customer statistic used as a feature is computed from
    observed payment history, never copied from the source system."""
    tally, _ = connector("customers")
    customer = tally.get_customers(ORG)[0]

    assert customer.average_delay_days is None
    assert customer.relationship_duration_days is None


# --------------------------------------------------------------- invoices


def test_invoices_map_to_canonical():
    tally, _ = connector("invoices")
    invoices = {i.invoice_id: i for i in tally.get_invoices(ORG)}

    assert set(invoices) == {"INV-1023", "INV-1038", "INV-0999"}
    assert invoices["INV-1023"].customer_id == "ABC Logistics Pvt Ltd"
    assert invoices["INV-1023"].invoice_amount == Decimal("412000.00")


def test_due_date_comes_from_the_bill_credit_period():
    """MSMED counts from the agreed credit period, so it has to be real.

    Defaulting it would hand check_msmed_threshold the full statutory 45 days
    for every invoice regardless of its actual terms.
    """
    tally, _ = connector("invoices")
    invoices = {i.invoice_id: i for i in tally.get_invoices(ORG)}

    # 2026-06-01 + 45 days
    assert invoices["INV-1023"].due_date == date(2026, 7, 16)
    # "30" without the word Days must parse the same as "30 Days"
    assert invoices["INV-1038"].due_date == date(2026, 7, 15)


def test_a_receivable_amount_is_positive_despite_tallys_credit_sign():
    tally, _ = connector("invoices")
    assert all(i.invoice_amount >= 0 for i in tally.get_invoices(ORG))


def test_payment_status_follows_the_outstanding_balance():
    tally, _ = connector("invoices")
    invoices = {i.invoice_id: i for i in tally.get_invoices(ORG)}

    assert invoices["INV-1023"].payment_status is PaymentStatus.PENDING
    assert invoices["INV-1038"].payment_status is PaymentStatus.PARTIALLY_PAID
    assert invoices["INV-0999"].payment_status is PaymentStatus.PAID


def test_invoice_amount_is_the_original_not_the_remainder():
    """A part-paid bill is still an invoice for its full value."""
    tally, _ = connector("invoices")
    invoices = {i.invoice_id: i for i in tally.get_invoices(ORG)}

    assert invoices["INV-1038"].invoice_amount == Decimal("880000.00")


def test_acceptance_date_is_left_unset_rather_than_invented():
    """Tally records no buyer acceptance; it is a TReDS/MSMED concept."""
    tally, _ = connector("invoices")
    assert all(i.acceptance_date is None for i in tally.get_invoices(ORG))


# --------------------------------------------------------------- payments


def test_payments_come_from_bill_allocations():
    tally, _ = connector("payments", "invoices")
    payments = tally.get_payments(ORG)

    assert {p.invoice_id for p in payments} == {"INV-0999", "INV-1038"}


def test_days_delayed_is_computed_against_the_bills_due_date():
    """The single most important field the delay model trains on."""
    tally, _ = connector("payments", "invoices")
    payments = {p.invoice_id: p for p in tally.get_payments(ORG)}

    # INV-0999: due 2026-04-01 + 30 days = 05-01, paid 05-20 → 19 days late.
    assert payments["INV-0999"].due_date == date(2026, 5, 1)
    assert payments["INV-0999"].days_delayed == 19


def test_a_payment_with_no_matching_bill_keeps_days_delayed_unset():
    """A fabricated zero would enter the training set as an on-time payment."""
    orphan = fixture("payments").replace("INV-0999", "INV-NOT-IN-BOOK")
    transport = RecordedTallyTransport([orphan, fixture("invoices")])
    tally = TallyConnector(TallyConfig(company="X"), transport=transport, as_of=AS_OF)

    payments = {p.invoice_id: p for p in tally.get_payments(ORG)}
    assert payments["INV-NOT-IN-BOOK"].days_delayed is None


def test_payment_amounts_are_positive():
    tally, _ = connector("payments", "invoices")
    assert all(p.payment_amount > 0 for p in tally.get_payments(ORG))


# --------------------------------------------------------------- requests


def test_requests_name_the_configured_company():
    tally, transport = connector("customers")
    tally.get_customers(ORG)

    assert "<SVCURRENTCOMPANY>Demo Supplier Pvt Ltd</SVCURRENTCOMPANY>" in transport.sent[0]


def test_requests_are_export_collections():
    tally, transport = connector("customers")
    tally.get_customers(ORG)

    assert "<TALLYREQUEST>Export</TALLYREQUEST>" in transport.sent[0]
    assert "<TYPE>Collection</TYPE>" in transport.sent[0]


def test_a_company_name_with_an_ampersand_is_escaped():
    """Otherwise the request envelope is malformed XML and Tally rejects it.

    Indian company names carry ampersands often enough that an unescaped one is
    a matter of when, not if.
    """
    xml = requests.customers_request("Sharma & Sons Pvt Ltd")

    assert "Sharma &amp; Sons Pvt Ltd" in xml
    # The real assertion: it is still well-formed XML.
    ElementTree.fromstring(xml)


def test_the_history_window_is_bounded_by_the_configured_days():
    transport = RecordedTallyTransport([fixture("invoices")])
    tally = TallyConnector(
        TallyConfig(company="X", history_days=90), transport=transport, as_of=AS_OF
    )
    tally.get_invoices(ORG)

    assert "<SVFROMDATE>20260518</SVFROMDATE>" in transport.sent[0]
    assert "<SVTODATE>20260816</SVTODATE>" in transport.sent[0]


# --------------------------------------------------------------- expenses


def test_expenses_map_to_plain_dicts():
    tally, _ = connector("expenses")
    expenses = tally.get_expenses(ORG)

    assert expenses == [
        {"name": "Salaries", "group": "Indirect Expenses", "amount": Decimal("1800000.00")}
    ]


# --------------------------------------------------------------- transport


def test_an_unreachable_gateway_raises_connector_unavailable():
    """The likeliest real failure: Tally is running but its gateway is off.

    Distinguished from ConnectorRejected on purpose — this one is retryable and
    is fixed in Tally's settings, whereas a rejection is a bad request.
    """
    from app.connectors.errors import ConnectorUnavailable
    from app.connectors.tally.transport import HttpTallyTransport

    # Port 1 is reserved and never has a listener.
    transport = HttpTallyTransport("http://127.0.0.1:1", timeout_s=2.0)

    with pytest.raises(ConnectorUnavailable) as exc:
        transport.send("<ENVELOPE/>")

    assert "gateway" in str(exc.value)


def test_the_swap_point_reads_through_the_connector(monkeypatch):
    """_load_portfolio is the single seam between synthetic and a live sync.

    Asserted here because CLAUDE.md makes that claim about the architecture and
    nothing else would catch it silently becoming untrue.
    """
    from app.config import settings
    from app.connectors.tally import connector as connector_module
    from app.decision_engine import service

    monkeypatch.setattr(settings, "portfolio_source", "tally")
    monkeypatch.setattr(settings, "tally_company", "Demo Supplier Pvt Ltd")
    monkeypatch.setattr(
        connector_module,
        "HttpTallyTransport",
        lambda *a, **k: RecordedTallyTransport(
            [fixture("customers"), fixture("invoices"), fixture("payments"), fixture("invoices")]
        ),
    )

    data = service._load_portfolio("ORG-DEMO")

    assert [c.customer_name for c in data.customers] == [
        "ABC Logistics Pvt Ltd",
        "Global Retail Ltd",
    ]
    assert {i.invoice_id for i in data.invoices} == {"INV-1023", "INV-1038", "INV-0999"}


def test_the_swap_point_refuses_tally_without_a_company_name(monkeypatch):
    """Tally returns an empty book for an unknown company rather than an error.

    Left unchecked that would surface as an empty action queue reading as
    "nothing to collect today".
    """
    from app.config import settings
    from app.decision_engine import service

    monkeypatch.setattr(settings, "portfolio_source", "tally")
    monkeypatch.setattr(settings, "tally_company", "")

    with pytest.raises(RuntimeError, match="tally_company"):
        service._load_portfolio("ORG-DEMO")
