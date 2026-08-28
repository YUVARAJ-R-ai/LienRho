"""Assembles the action queue from every layer (FR-009).

This is the seam where connectors, ML, rules, and the decision engine meet.
It currently reads the synthetic demo dataset rather than a live Tally sync —
swapping in the connector means changing `_load_portfolio` and nothing else.

The queue itself is derived on every request. Human decisions and their audit
trails are not — they live in an `ApprovalStore` (see `store.py`) and are
replayed onto each rebuild, so they survive an API restart (FR-014, NFR-007).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache

from app.agents.investigator import get_investigator
from app.agents.strategy import StrategyContext, get_strategist
from app.config import settings
from app.data.communications import build_threads
from app.data.synthetic import (
    AS_OF,
    DEFAULT_ORG_ID,
    DEMO_SUPPLIER,
    GeneratedDataset,
    generate_dataset,
)
from app.decision_engine.engine import (
    ActionRecommendation,
    RecommendedAction,
    approve,
    build_recommendation,
    rank_queue,
    reject,
)
from app.decision_engine.store import ApprovalRecord, get_approval_store
from app.ml_core.features import build_customer_stats, extract_features
from app.ml_core.forecast import build_forecast
from app.ml_core.model import DEFAULT_MODEL_PATH, DelayModel
from app.outreach.dossier import EscalationDossier, build_dossier
from app.outreach.drafts import DraftChannel, DraftContext, ReminderDraft, get_drafter
from app.outreach.treds_submission import TredsSubmission, build_treds_submission
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


# --------------------------------------------------------------- approvals


def reset_approvals(org_id: str | None = None) -> None:
    """Forget every recorded decision. For tests and demo resets."""
    get_approval_store().clear(org_id)


def _apply_approval(
    recommendation: ActionRecommendation, *, org_id: str
) -> ActionRecommendation:
    """Replay any recorded decision onto a freshly built recommendation.

    The queue is derived on every request, so this is what keeps the *human*
    part of it — the decision and its audit trail — from being recomputed away.
    """
    record = get_approval_store().get(org_id, recommendation.invoice_id)
    if record is None:
        return recommendation
    recommendation.approval_state = record.state
    recommendation.audit_trail.extend(record.entries)
    return recommendation


def decide_on_action(
    invoice_id: str,
    *,
    approved: bool,
    actor: str,
    as_of: date = AS_OF,
    org_id: str = DEFAULT_ORG_ID,
) -> ActionRecommendation | None:
    """Record an explicit human approval or rejection (FR-010, BR-APPROVAL).

    Returns None when the invoice isn't in the queue. Rejecting deliberately
    changes nothing about the invoice itself — only the recorded decision and
    the audit trail (FR-010 AC-2).
    """
    recommendation = next(
        (
            r
            for r in build_action_queue(as_of=as_of, org_id=org_id)
            if r.invoice_id == invoice_id
        ),
        None,
    )
    if recommendation is None:
        return None

    store = get_approval_store()
    existing = store.get(org_id, invoice_id)

    # Everything already on the trail was either derived this call or replayed
    # from earlier decisions; only what the decision below appends is new.
    prior = list(existing.entries) if existing else []
    boundary = len(recommendation.audit_trail)

    if approved:
        approve(recommendation, actor=actor)
    else:
        reject(recommendation, actor=actor)

    # Keep the full sequence, not just the latest: an approve-then-reject is two
    # facts about who decided what, and FR-014 asks for both.
    store.record(
        org_id,
        invoice_id,
        ApprovalRecord(
            state=recommendation.approval_state,
            entries=prior + recommendation.audit_trail[boundary:],
            recommended_action=recommendation.recommended_action,
            actor=actor,
        ),
    )
    return recommendation


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


def _load_portfolio(org_id: str = DEFAULT_ORG_ID):
    """Current open invoices, customers, and payment history.

    The single swap point between the demo dataset and a live accounting sync
    (FR-001). Everything downstream sees canonical types either way, so nothing
    else in the pipeline changes when this switches.

    `settings.portfolio_source` chooses: `synthetic` (default) generates the
    demo portfolio, `tally` reads a live company on every request, `database`
    reads the canonical store that `POST /api/sync` populates.

    Defaults to synthetic: `TallyConnector` is implemented and tested against
    recorded fixtures, but ASM-01 — whether Tally's gateway is actually
    reachable this way — has never been checked against a live instance.
    """
    if settings.portfolio_source == "database":
        return _load_from_database(org_id)
    if settings.portfolio_source == "tally":
        return _load_from_connector(org_id, "tally")
    return generate_dataset(org_id=org_id)


def _load_from_database(org_id: str) -> GeneratedDataset:
    """Read the canonical store, populated by a connector sync (FR-001).

    The shape FR-001 actually describes: the connector writes to the store on
    its own schedule, and the queue reads the store. It decouples serving a
    request from an accounting system being up.
    """
    from app.db.session import SessionLocal
    from app.sync import load_portfolio

    with SessionLocal() as session:
        return load_portfolio(session, org_id=org_id)


def _load_from_connector(org_id: str, source: str) -> GeneratedDataset:
    """Read straight through a connector, without persisting.

    Returns the same container the synthetic path does rather than a new type —
    the point of the canonical layer is that the caller cannot tell which
    source it got.
    """
    from app.connectors import get_connector

    connector = get_connector(source)
    return GeneratedDataset(
        customers=connector.get_customers(org_id),
        invoices=connector.get_invoices(org_id),
        payments=connector.get_payments(org_id),
    )


def build_action_queue(
    as_of: date = AS_OF, org_id: str = DEFAULT_ORG_ID
) -> list[ActionRecommendation]:
    """Score, evaluate, and rank every open invoice into the daily queue."""
    data = _load_portfolio(org_id)
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

    forecast = get_cash_forecast(as_of=as_of, org_id=org_id)
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

    return rank_queue([_apply_approval(r, org_id=org_id) for r in recommendations])


def get_cash_forecast(as_of: date = AS_OF, org_id: str = DEFAULT_ORG_ID):
    """30-day forecast over the current portfolio (FR-004, FR-015)."""
    from app.canonical.models import BusinessFinancialState

    data = _load_portfolio(org_id)
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
        org_id=org_id,
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


def get_investigation(
    invoice_id: str, as_of: date = AS_OF, org_id: str = DEFAULT_ORG_ID
) -> dict | None:
    """Full detail for one invoice (FR-003, FR-007, FR-014)."""
    data = _load_portfolio(org_id)
    invoice = next((i for i in data.invoices if i.invoice_id == invoice_id), None)
    if invoice is None:
        return None

    recommendation = next(
        (
            r
            for r in build_action_queue(as_of=as_of, org_id=org_id)
            if r.invoice_id == invoice_id
        ),
        None,
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


def get_findings(invoice_id: str, as_of: date = AS_OF, org_id: str = DEFAULT_ORG_ID):
    """Investigator findings for one invoice, for the investigation screen."""
    data = _load_portfolio(org_id)
    threads = build_threads(data.invoices)
    thread = threads.get(invoice_id)
    if thread is None:
        return None
    return get_investigator().investigate(thread, as_of=as_of)


# --------------------------------------------------------------- artifacts


def build_draft(
    invoice_id: str,
    *,
    channel: DraftChannel = DraftChannel.EMAIL,
    as_of: date = AS_OF,
    org_id: str = DEFAULT_ORG_ID,
) -> ReminderDraft | None:
    """Draft a reminder for one invoice (FR-011).

    Deliberately not gated on approval: a draft is what the user reads *before*
    deciding, so requiring approval to see it would invert the review step this
    whole flow exists for. The approval gate sits in front of sending, and
    sending is the user's own action (OQ-01 → drafted-in-UI).
    """
    data = _load_portfolio(org_id)
    invoice = next((i for i in data.invoices if i.invoice_id == invoice_id), None)
    if invoice is None:
        return None

    customer = next(
        (c for c in data.customers if c.customer_id == invoice.customer_id), None
    )

    return get_drafter().draft(
        DraftContext(
            invoice_id=invoice.invoice_id,
            customer_name=customer.customer_name if customer else invoice.customer_id,
            invoice_amount=invoice.invoice_amount,
            due_date=invoice.due_date,
            days_overdue=max((as_of - invoice.due_date).days, 0),
            supplier_name=DEMO_SUPPLIER.legal_name,
            findings=get_findings(invoice_id, as_of=as_of, org_id=org_id),
        ),
        channel=channel,
    )


def build_artifact(
    recommendation: ActionRecommendation,
    *,
    as_of: date = AS_OF,
    org_id: str = DEFAULT_ORG_ID,
) -> ReminderDraft | TredsSubmission | EscalationDossier | None:
    """The artifact this recommendation's action produces (FR-011/012/013).

    Dispatches on the recommended action rather than taking a type argument, so
    a caller cannot ask for a dossier on an invoice the system recommended a
    reminder for. The gate lives inside each builder, not here — putting it in
    one place upstream would mean a new builder could quietly skip it.
    """
    data = _load_portfolio(org_id)
    invoice = next(
        (i for i in data.invoices if i.invoice_id == recommendation.invoice_id), None
    )
    if invoice is None:
        return None

    customer = next(
        (c for c in data.customers if c.customer_id == invoice.customer_id), None
    )

    if recommendation.recommended_action is RecommendedAction.FINANCE:
        return build_treds_submission(
            recommendation=recommendation,
            invoice=invoice,
            customer=customer,
            as_of=as_of,
        )

    if recommendation.recommended_action is RecommendedAction.ESCALATE:
        return build_dossier(
            recommendation=recommendation,
            invoice=invoice,
            customer=customer,
            supplier=DEMO_SUPPLIER,
            payments=data.payments,
            thread=build_threads(data.invoices).get(invoice.invoice_id),
            as_of=as_of,
        )

    return build_draft(invoice.invoice_id, as_of=as_of, org_id=org_id)
