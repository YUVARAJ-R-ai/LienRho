"""Assembles the action queue from every layer (FR-009).

This is the seam where connectors, ML, rules, and the decision engine meet.
It currently reads the synthetic demo dataset rather than a live Tally sync —
swapping in the connector means changing `_load_portfolio` and nothing else.

Recommendations are held in memory for the demo. Persisting them (and their
audit trails) to Postgres is FR-014's remaining backend work.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache

from app.agents.investigator import get_investigator
from app.agents.strategy import StrategyContext, get_strategist
from app.data.communications import build_threads
from app.data.synthetic import AS_OF, generate_dataset
from app.decision_engine.engine import (
    ActionRecommendation,
    build_recommendation,
    rank_queue,
)
from app.ml_core.features import build_customer_stats, extract_features
from app.ml_core.forecast import build_forecast
from app.ml_core.model import DEFAULT_MODEL_PATH, DelayModel
from app.rules_engine.msmed import calculate_appointed_day, check_msmed_threshold
from app.rules_engine.treds import check_treds_eligibility

# Demo business state. Real values come from the connector's ledger read (FR-001);
# the canonical model carries these as monthly aggregates today.
#
# These are set to a plausibly tight MSME running against a Rs 42.6L receivables
# book — which is the situation the product exists for. The shortfall date is
# NOT tuned to hit a particular number: it falls wherever the model's predicted
# inflows and these obligations intersect. prd.md §37's "Rs 6.2L in 14 days" is
# an illustrative scenario (inception.md flags the rupee figures as unvalidated),
# so reverse-engineering the state to reproduce it exactly would be dishonest.
DEMO_STATE_CASH = Decimal(1850000)
DEMO_CASH_THRESHOLD = Decimal(500000)
DEMO_UPCOMING_EXPENSES = Decimal(1800000)
DEMO_PAYROLL = Decimal(1800000)
DEMO_SUPPLIER_PAYMENTS = Decimal(2600000)

# An invoice only counts as driving the shortfall if it's genuinely likely to
# still be unpaid at the breach. Below this, it's a large invoice that will
# probably arrive in time, not a cause.
MATERIAL_SHORTFALL_RISK = 0.5


@lru_cache(maxsize=1)
def _load_model() -> DelayModel | None:
    """Load the trained model once per process.

    Returns None when no artifact exists so the API degrades to rule-only
    recommendations rather than failing outright — a teammate who hasn't run
    training yet should still get a working app.
    """
    if not DEFAULT_MODEL_PATH.exists():
        return None
    try:
        return DelayModel.load()
    except Exception:  # noqa: BLE001 - a corrupt artifact must not break the API
        return None


def _load_portfolio():
    """Current open invoices, customers, and payment history.

    Replace with a connector sync (FR-001) when the Tally adapter lands.
    """
    return generate_dataset()


def build_action_queue(as_of: date = AS_OF) -> list[ActionRecommendation]:
    """Score, evaluate, and rank every open invoice into the daily queue."""
    data = _load_portfolio()
    model = _load_model()
    stats = build_customer_stats(data.payments)
    customers = {c.customer_id: c for c in data.customers}

    # Predictions first: the forecast needs them to weight expected inflows.
    predictions: dict[str, dict[str, float]] = {}
    probability_over_45: dict[str, float] = {}

    for invoice in data.invoices:
        if model is None:
            continue
        features = extract_features(
            invoice=invoice,
            customer=customers.get(invoice.customer_id),
            stats=stats.get(invoice.customer_id),
        )
        prediction = model.predict(features)
        predictions[invoice.invoice_id] = prediction.probabilities
        probability_over_45[invoice.invoice_id] = prediction.probability_over_45_days

    forecast = get_cash_forecast(as_of=as_of)
    # Only *material* contributors escalate an invoice to Critical. Every open
    # invoice contributes some probability mass to a shortfall, so ranking alone
    # would mark low-risk invoices critical purely for being large.
    shortfall_ids = (
        {
            c.invoice_id
            for c in forecast.contributors[:5]
            if c.probability_unpaid_by_shortfall >= MATERIAL_SHORTFALL_RISK
        }
        if forecast.has_shortfall
        else set()
    )

    portfolio_max = max((i.invoice_amount for i in data.invoices), default=Decimal(1))

    # Communication evidence (FR-007). The rule-based investigator runs with no
    # external dependency, so this layer works before OQ-02 resolves.
    threads = build_threads(data.invoices)
    investigator = get_investigator()
    findings = {
        invoice.invoice_id: investigator.investigate(
            threads[invoice.invoice_id], as_of=as_of
        )
        for invoice in data.invoices
        if invoice.invoice_id in threads
    }

    strategist = get_strategist()

    recommendations = []
    for invoice in data.invoices:
        acceptance = invoice.acceptance_date or invoice.invoice_date
        msmed = check_msmed_threshold(
            acceptance_date=acceptance,
            as_of=as_of,
            buyer_is_registered_enterprise=True,
            supplier_is_msme=True,
            # MSMED §15 makes the appointed day the *agreed* credit period,
            # capped at 45 days. Omitting it would wrongly grant every invoice
            # the full statutory 45 days regardless of its actual terms.
            agreed_credit_days=(invoice.due_date - invoice.invoice_date).days,
        )
        customer = customers.get(invoice.customer_id)
        treds = check_treds_eligibility(
            invoice_amount=invoice.invoice_amount,
            due_date=invoice.due_date,
            as_of=as_of,
            invoice_is_buyer_approved=invoice.acceptance_date is not None,
            buyer_participates_in_treds=(
                customer.treds_status == "PARTICIPANT" if customer else False
            ),
            supplier_is_msme=True,
        )

        # The strategist gathers statutory and financing facts through the tool
        # boundary, so every figure below is traceable to a named function.
        strategy = strategist.recommend(
            StrategyContext(
                invoice_id=invoice.invoice_id,
                invoice_amount=invoice.invoice_amount,
                due_date=invoice.due_date,
                invoice_date=invoice.invoice_date,
                acceptance_date=acceptance,
                buyer_participates_in_treds=(
                    customer.treds_status == "PARTICIPANT" if customer else False
                ),
                probability_over_45=probability_over_45.get(invoice.invoice_id, 0.0),
                shortfall_projected=forecast.has_shortfall,
                contributes_to_shortfall=invoice.invoice_id in shortfall_ids,
                findings=_finding(findings, invoice),
            ),
            as_of=as_of,
        )

        recommendations.append(
            build_recommendation(
                invoice=invoice,
                customer_name=customer.customer_name if customer else invoice.customer_id,
                as_of=as_of,
                delay_probabilities=predictions.get(invoice.invoice_id, {}),
                probability_over_45=probability_over_45.get(invoice.invoice_id, 0.0),
                statutory_flag=msmed["statutory_flag"],
                statutory_reason=msmed["reason"],
                treds_eligible=treds["eligible"],
                treds_reason=treds["reason"],
                contributes_to_shortfall=invoice.invoice_id in shortfall_ids,
                shortfall_projected=forecast.has_shortfall,
                portfolio_max_amount=portfolio_max,
                payment_promise=_finding(findings, invoice).payment_promise
                if _finding(findings, invoice)
                else False,
                promise_is_credible=_finding(findings, invoice).promise_is_credible
                if _finding(findings, invoice)
                else True,
                dispute_detected=_finding(findings, invoice).dispute_detected
                if _finding(findings, invoice)
                else False,
                findings_summary=_summarize_findings(_finding(findings, invoice)),
                tool_trace=strategy.trace,
            )
        )

    return rank_queue(recommendations)


def get_cash_forecast(as_of: date = AS_OF):
    """30-day forecast over the current portfolio (FR-004, FR-015)."""
    from app.canonical.models import BusinessFinancialState

    data = _load_portfolio()
    model = _load_model()
    stats = build_customer_stats(data.payments)
    customers = {c.customer_id: c for c in data.customers}

    predictions: dict[str, dict[str, float]] = {}
    if model is not None:
        for invoice in data.invoices:
            features = extract_features(
                invoice=invoice,
                customer=customers.get(invoice.customer_id),
                stats=stats.get(invoice.customer_id),
            )
            predictions[invoice.invoice_id] = model.predict(features).probabilities

    state = BusinessFinancialState(
        org_id="ORG-DEMO",
        as_of_date=as_of,
        current_cash=DEMO_STATE_CASH,
        expected_inflows=Decimal(0),
        upcoming_expenses=DEMO_UPCOMING_EXPENSES,
        payroll=DEMO_PAYROLL,
        supplier_payments=DEMO_SUPPLIER_PAYMENTS,
        cash_threshold=DEMO_CASH_THRESHOLD,
    )

    return build_forecast(
        state=state,
        invoices=data.invoices,
        predictions=predictions,
        as_of=as_of,
    )


def get_investigation(invoice_id: str, as_of: date = AS_OF) -> dict | None:
    """Full detail for one invoice (FR-003, FR-007, FR-014)."""
    data = _load_portfolio()
    invoice = next((i for i in data.invoices if i.invoice_id == invoice_id), None)
    if invoice is None:
        return None

    recommendation = next(
        (r for r in build_action_queue(as_of=as_of) if r.invoice_id == invoice_id), None
    )

    model = _load_model()
    stats = build_customer_stats(data.payments)
    customers = {c.customer_id: c for c in data.customers}
    customer = customers.get(invoice.customer_id)

    factors: list[dict] = []
    if model is not None:
        features = extract_features(
            invoice=invoice, customer=customer, stats=stats.get(invoice.customer_id)
        )
        factors = model.predict(features).top_factors

    acceptance = invoice.acceptance_date or invoice.invoice_date
    agreed_credit_days = (invoice.due_date - invoice.invoice_date).days
    msmed = check_msmed_threshold(
        acceptance_date=acceptance,
        as_of=as_of,
        buyer_is_registered_enterprise=True,
        supplier_is_msme=True,
        agreed_credit_days=agreed_credit_days,
    )
    treds = check_treds_eligibility(
        invoice_amount=invoice.invoice_amount,
        due_date=invoice.due_date,
        as_of=as_of,
        invoice_is_buyer_approved=invoice.acceptance_date is not None,
        buyer_participates_in_treds=(
            customer.treds_status == "PARTICIPANT" if customer else False
        ),
        supplier_is_msme=True,
    )

    statutory_interest = None
    if msmed["statutory_flag"]:
        from app.rules_engine.msmed import calculate_interest

        statutory_interest = calculate_interest(
            principal=invoice.invoice_amount,
            appointed_day=calculate_appointed_day(acceptance, agreed_credit_days),
            as_of=as_of,
            # RBI bank rate at the time of the demo scenario.
            rbi_bank_rate=Decimal("0.065"),
        )

    return {
        "invoice": invoice,
        "customer": customer,
        "recommendation": recommendation,
        "factors": factors,
        "msmed": msmed,
        "statutory_interest": statutory_interest,
        "treds": treds,
    }


def _finding(findings: dict, invoice):
    return findings.get(invoice.invoice_id)


def _summarize_findings(finding) -> str | None:
    """One audit-trail line describing what the Investigator concluded."""
    if finding is None:
        return None

    if finding.dispute_detected:
        return f"Dispute detected — {finding.dispute_summary or 'customer contests the invoice'}"

    if finding.payment_promise:
        when = f" for {finding.promised_date}" if finding.promised_date else ""
        if not finding.promise_is_credible:
            return (
                f"Payment promised{when}, but {finding.prior_broken_promises} prior "
                "promise(s) were not kept"
            )
        return f"Payment promised{when}, no dispute on record"

    return "No payment promise or dispute found in correspondence"


def get_findings(invoice_id: str, as_of: date = AS_OF):
    """Investigator findings for one invoice, for the investigation screen."""
    data = _load_portfolio()
    threads = build_threads(data.invoices)
    thread = threads.get(invoice_id)
    if thread is None:
        return None
    return get_investigator().investigate(thread, as_of=as_of)
