from datetime import date, timedelta
from decimal import Decimal

from app.canonical.models import BusinessFinancialState, CanonicalInvoice, PaymentStatus
from app.ml_core.forecast import (
    build_forecast,
    condition_on_still_unpaid,
    probability_paid_by,
    rank_shortfall_contributors,
)

AS_OF = date(2026, 8, 15)

# Certain to arrive within 15 days of the due date.
CERTAIN_FAST = {"0-15 days": 1.0, "16-30 days": 0.0, "31-45 days": 0.0, ">45 days": 0.0}
# Certain never to arrive inside the horizon.
CERTAIN_SLOW = {"0-15 days": 0.0, "16-30 days": 0.0, "31-45 days": 0.0, ">45 days": 1.0}
SPLIT = {"0-15 days": 0.5, "16-30 days": 0.2, "31-45 days": 0.1, ">45 days": 0.2}


def _invoice(invoice_id="INV-1", amount=Decimal(100000), due_offset=0, customer="CUST-1"):
    due = AS_OF + timedelta(days=due_offset)
    return CanonicalInvoice(
        org_id="ORG-TEST",
        invoice_id=invoice_id,
        customer_id=customer,
        invoice_amount=amount,
        invoice_date=due - timedelta(days=30),
        due_date=due,
        acceptance_date=due - timedelta(days=29),
        payment_status=PaymentStatus.PENDING,
        payment_date=None,
    )


def _state(cash=Decimal(1000000), threshold=Decimal(500000), expenses=Decimal(0)):
    return BusinessFinancialState(
        org_id="ORG-TEST",
        as_of_date=AS_OF,
        current_cash=cash,
        expected_inflows=Decimal(0),
        upcoming_expenses=expenses,
        payroll=Decimal(0),
        supplier_payments=Decimal(0),
        cash_threshold=threshold,
    )


# ------------------------------------------------------- probability_paid_by


def test_nothing_is_paid_before_the_due_date():
    assert (
        probability_paid_by(
            delay_probabilities=CERTAIN_FAST,
            due_date=AS_OF + timedelta(days=10),
            target_day=AS_OF,
        )
        == 0.0
    )


def test_fast_bucket_counts_once_its_window_has_elapsed():
    p = probability_paid_by(
        delay_probabilities=CERTAIN_FAST, due_date=AS_OF, target_day=AS_OF + timedelta(days=15)
    )
    assert p == 1.0


def test_fast_bucket_does_not_count_before_its_window_closes():
    p = probability_paid_by(
        delay_probabilities=CERTAIN_FAST, due_date=AS_OF, target_day=AS_OF + timedelta(days=14)
    )
    assert p == 0.0


# The open-ended bucket must never be counted as arrived inside the horizon,
# otherwise the forecast invents cash that may never come.
def test_over_45_day_bucket_never_counts_within_the_horizon():
    p = probability_paid_by(
        delay_probabilities=CERTAIN_SLOW, due_date=AS_OF, target_day=AS_OF + timedelta(days=30)
    )
    assert p == 0.0


def test_partial_buckets_accumulate():
    p = probability_paid_by(
        delay_probabilities=SPLIT, due_date=AS_OF, target_day=AS_OF + timedelta(days=30)
    )
    assert abs(p - 0.7) < 1e-9  # 0-15 plus 16-30


def test_probability_never_exceeds_one():
    weird = {"0-15 days": 0.9, "16-30 days": 0.9, "31-45 days": 0.9, ">45 days": 0.0}
    p = probability_paid_by(
        delay_probabilities=weird, due_date=AS_OF, target_day=AS_OF + timedelta(days=45)
    )
    assert p == 1.0


# ------------------------------------------------------------------ forecast


def test_forecast_covers_the_full_horizon_inclusive():
    forecast = build_forecast(
        state=_state(), invoices=[], predictions={}, as_of=AS_OF, horizon_days=30
    )
    assert len(forecast.points) == 31
    assert forecast.points[0].day == AS_OF
    assert forecast.points[-1].day == AS_OF + timedelta(days=30)


def test_no_shortfall_when_cash_stays_above_threshold():
    forecast = build_forecast(
        state=_state(cash=Decimal(1000000), threshold=Decimal(100000)),
        invoices=[],
        predictions={},
        as_of=AS_OF,
    )
    assert forecast.has_shortfall is False
    assert forecast.shortfall_date is None


def test_shortfall_detected_when_expenses_drain_cash():
    forecast = build_forecast(
        state=_state(cash=Decimal(600000), threshold=Decimal(500000), expenses=Decimal(900000)),
        invoices=[],
        predictions={},
        as_of=AS_OF,
    )
    assert forecast.has_shortfall is True
    assert forecast.shortfall_amount > 0


def test_forecast_reports_only_the_earliest_breach():
    forecast = build_forecast(
        state=_state(cash=Decimal(600000), threshold=Decimal(500000), expenses=Decimal(3000000)),
        invoices=[],
        predictions={},
        as_of=AS_OF,
    )
    # Once it dips it stays down; the reported date must be the first crossing.
    first_below = next(p.day for p in forecast.points if p.projected_cash < Decimal(500000))
    assert forecast.shortfall_date == first_below


def test_expected_inflow_rises_as_invoices_come_due():
    invoice = _invoice(amount=Decimal(400000), due_offset=0)
    forecast = build_forecast(
        state=_state(),
        invoices=[invoice],
        predictions={"INV-1": CERTAIN_FAST},
        as_of=AS_OF,
    )
    assert forecast.points[0].expected_inflow_to_date == Decimal("0.00")
    assert forecast.points[-1].expected_inflow_to_date == Decimal("400000.00")


def test_slow_paying_invoice_contributes_no_inflow():
    forecast = build_forecast(
        state=_state(),
        invoices=[_invoice(amount=Decimal(400000))],
        predictions={"INV-1": CERTAIN_SLOW},
        as_of=AS_OF,
    )
    assert forecast.points[-1].expected_inflow_to_date == Decimal("0.00")


def test_invoice_without_a_prediction_contributes_nothing():
    # Better to under-promise cash than invent it.
    forecast = build_forecast(
        state=_state(), invoices=[_invoice()], predictions={}, as_of=AS_OF
    )
    assert forecast.points[-1].expected_inflow_to_date == Decimal("0.00")


def test_expected_inflow_prevents_a_shortfall_that_would_otherwise_occur():
    """Inflow only helps if it lands before cash runs out — timing matters.

    Burn here is slow enough (Rs 20k/day against a Rs 4L buffer) that the
    breach would fall around day 21, after the invoice's 0-15 day window.
    """
    state = {"cash": Decimal(900000), "threshold": Decimal(500000), "expenses": Decimal(600000)}
    without = build_forecast(
        state=_state(**state),
        invoices=[_invoice(amount=Decimal(2000000))],
        predictions={},
        as_of=AS_OF,
    )
    # Due today, so the 0-15 day bucket is still live and can be counted.
    with_inflow = build_forecast(
        state=_state(**state),
        invoices=[_invoice(amount=Decimal(2000000), due_offset=0)],
        predictions={"INV-1": CERTAIN_FAST},
        as_of=AS_OF,
    )
    assert without.has_shortfall is True
    assert with_inflow.has_shortfall is False


def test_inflow_arriving_after_the_breach_does_not_prevent_it():
    """The mirror case: cash can run out before a certain payment lands."""
    forecast = build_forecast(
        state=_state(cash=Decimal(600000), threshold=Decimal(500000), expenses=Decimal(900000)),
        invoices=[_invoice(amount=Decimal(2000000), due_offset=0)],
        predictions={"INV-1": CERTAIN_FAST},
        as_of=AS_OF,
    )
    assert forecast.has_shortfall is True
    # Breach lands before the invoice's 15-day payment window closes.
    assert forecast.shortfall_date < AS_OF + timedelta(days=15)


# ------------------------------------------------------- FR-015 contributors


def test_contributors_ranked_by_contribution_descending():
    invoices = [
        _invoice("INV-A", Decimal(100000)),
        _invoice("INV-B", Decimal(500000)),
        _invoice("INV-C", Decimal(250000)),
    ]
    ranked = rank_shortfall_contributors(
        invoices=invoices,
        predictions={i.invoice_id: CERTAIN_SLOW for i in invoices},
        shortfall_date=AS_OF + timedelta(days=20),
        as_of=AS_OF,
    )
    amounts = [c.contribution for c in ranked]
    assert amounts == sorted(amounts, reverse=True)
    assert ranked[0].invoice_id == "INV-B"


def test_invoice_certain_to_arrive_in_time_is_not_a_contributor():
    # Not yet due, so its fast bucket survives conditioning and it lands in time.
    ranked = rank_shortfall_contributors(
        invoices=[_invoice("INV-A", Decimal(500000), due_offset=0)],
        predictions={"INV-A": CERTAIN_FAST},
        shortfall_date=AS_OF + timedelta(days=16),
        as_of=AS_OF,
    )
    assert ranked == []


def test_large_likely_invoice_ranks_below_smaller_unlikely_one():
    # Contribution is amount x probability-unpaid, not raw amount.
    likely_big = _invoice("INV-BIG", Decimal(1000000), due_offset=0)
    unlikely_small = _invoice("INV-SMALL", Decimal(300000))
    ranked = rank_shortfall_contributors(
        invoices=[likely_big, unlikely_small],
        predictions={"INV-BIG": CERTAIN_FAST, "INV-SMALL": CERTAIN_SLOW},
        shortfall_date=AS_OF + timedelta(days=16),
        as_of=AS_OF,
    )
    assert ranked[0].invoice_id == "INV-SMALL"


def test_contributors_are_populated_on_a_forecast_with_a_shortfall():
    forecast = build_forecast(
        state=_state(cash=Decimal(600000), threshold=Decimal(500000), expenses=Decimal(900000)),
        invoices=[_invoice("INV-A", Decimal(400000))],
        predictions={"INV-A": CERTAIN_SLOW},
        as_of=AS_OF,
    )
    assert forecast.has_shortfall
    assert forecast.contributors
    assert forecast.contributors[0].invoice_id == "INV-A"


def test_no_contributors_when_there_is_no_shortfall():
    forecast = build_forecast(
        state=_state(cash=Decimal(5000000), threshold=Decimal(100000)),
        invoices=[_invoice()],
        predictions={"INV-1": CERTAIN_SLOW},
        as_of=AS_OF,
    )
    assert forecast.contributors == []


# ------------------------------------------- conditioning on still-being-unpaid


def test_conditioning_is_a_no_op_before_the_due_date():
    assert condition_on_still_unpaid(SPLIT, 0) == SPLIT


def test_elapsed_bucket_mass_is_removed_and_redistributed():
    # 20 days overdue means "paid within 0-15 days" has already been falsified.
    conditioned = condition_on_still_unpaid(SPLIT, 20)
    assert conditioned["0-15 days"] == 0.0
    assert abs(sum(conditioned.values()) - 1.0) < 1e-9
    # Surviving buckets keep their relative proportions.
    assert conditioned["16-30 days"] > SPLIT["16-30 days"]


def test_invoice_past_every_bucket_is_certainly_in_the_open_ended_one():
    conditioned = condition_on_still_unpaid(SPLIT, 90)
    assert conditioned[">45 days"] == 1.0


def test_conditioning_prevents_counting_cash_that_never_arrived():
    """The bug this guards: an overdue invoice paying its elapsed bucket as inflow.

    An invoice 40 days overdue whose model output is mostly "0-15 days" must not
    contribute that mass — we can observe it did not arrive in that window.
    """
    overdue = _invoice(amount=Decimal(1000000), due_offset=-40)
    forecast = build_forecast(
        state=_state(),
        invoices=[overdue],
        predictions={"INV-1": CERTAIN_FAST},
        as_of=AS_OF,
    )
    assert forecast.points[0].expected_inflow_to_date == Decimal("0.00")


def test_conditioned_forecast_is_more_conservative_than_unconditioned():
    overdue = _invoice(amount=Decimal(1000000), due_offset=-35)
    forecast = build_forecast(
        state=_state(),
        invoices=[overdue],
        predictions={"INV-1": SPLIT},
        as_of=AS_OF,
    )
    naive = probability_paid_by(
        delay_probabilities=SPLIT,
        due_date=overdue.due_date,
        target_day=AS_OF + timedelta(days=30),
    )
    conditioned_inflow = float(forecast.points[-1].expected_inflow_to_date)
    assert conditioned_inflow < naive * 1000000
