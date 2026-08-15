from decimal import Decimal
from statistics import mean

from app.data.synthetic import (
    TARGET_INVOICE_COUNT,
    TARGET_TOTAL,
    generate_dataset,
)


def test_dataset_matches_reference_portfolio_size():
    data = generate_dataset()
    assert len(data.invoices) == TARGET_INVOICE_COUNT


def test_dataset_totals_exactly_the_reference_amount():
    # prd.md §37 pins the portfolio at Rs 42.6L; the demo narration uses it.
    data = generate_dataset()
    assert sum(i.invoice_amount for i in data.invoices) == TARGET_TOTAL


def test_generation_is_deterministic_for_a_given_seed():
    a = generate_dataset(seed=42)
    b = generate_dataset(seed=42)
    assert [i.invoice_id for i in a.invoices] == [i.invoice_id for i in b.invoices]
    assert [i.invoice_amount for i in a.invoices] == [i.invoice_amount for i in b.invoices]


def test_different_seeds_produce_different_portfolios():
    a = generate_dataset(seed=1)
    b = generate_dataset(seed=2)
    assert [i.invoice_amount for i in a.invoices] != [i.invoice_amount for i in b.invoices]


def test_showcase_cases_are_present_with_exact_amounts():
    # The demo narrative depends on these three specific invoices.
    by_id = {i.invoice_id: i for i in generate_dataset().invoices}
    assert by_id["INV-1023"].invoice_amount == Decimal(480000)
    assert by_id["INV-1038"].invoice_amount == Decimal(320000)
    assert by_id["INV-1042"].invoice_amount == Decimal(210000)


def test_escalation_case_is_past_the_msmed_threshold():
    from app.data.synthetic import AS_OF

    by_id = {i.invoice_id: i for i in generate_dataset().invoices}
    apex = by_id["INV-1042"]
    assert (AS_OF - apex.due_date).days == 52


def test_all_invoices_carry_the_org_id():
    data = generate_dataset(org_id="ORG-TEST")
    assert all(i.org_id == "ORG-TEST" for i in data.invoices)
    assert all(c.org_id == "ORG-TEST" for c in data.customers)


def test_no_invoice_has_a_non_positive_amount():
    data = generate_dataset()
    assert all(i.invoice_amount > 0 for i in data.invoices)


def test_due_date_always_follows_invoice_date():
    data = generate_dataset()
    assert all(i.due_date > i.invoice_date for i in data.invoices)


def test_payment_history_exists_for_model_training():
    data = generate_dataset()
    assert len(data.payments) > 50


def test_generated_payment_history_carries_a_learnable_signal():
    # The whole point of the profiles is that a model can recover "this customer
    # pays late" from the history. If the generated delays didn't separate a
    # habitually-late payer from a prompt one, NFR-005's metrics would be
    # measuring noise.
    data = generate_dataset()

    delays: dict[str, list[int]] = {}
    for p in data.payments:
        delays.setdefault(p.customer_id, []).append(p.days_delayed)

    slow_mean = mean(delays["CUST-004"])  # profile mean 48 days
    fast_mean = mean(delays["CUST-008"])  # profile mean 5 days
    assert slow_mean > fast_mean + 20


def test_every_payment_is_attributed_to_a_known_customer():
    data = generate_dataset()
    known = {c.customer_id for c in data.customers}
    assert all(p.customer_id in known for p in data.payments)


def test_historical_payments_are_all_in_the_past():
    from app.data.synthetic import AS_OF

    data = generate_dataset()
    assert all(p.actual_payment_date < AS_OF for p in data.payments)
