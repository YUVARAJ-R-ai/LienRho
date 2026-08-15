"""API routes backing the four frontend screens."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    ActionQueueItemOut,
    AgentFindingsOut,
    CashForecastOut,
    ContributingInvoiceOut,
    DelayPredictionOut,
    ForecastPointOut,
    InvestigationOut,
    InvoiceOut,
    PortfolioSummaryOut,
    PredictionFactorOut,
    RuleFlagsOut,
)
from app.decision_engine.service import (
    build_action_queue,
    get_cash_forecast,
    get_investigation,
)
from app.ml_core.features import BUCKET_LABELS

router = APIRouter(prefix="/api", tags=["lienrho"])


def _prediction_out(probabilities: dict[str, float]) -> DelayPredictionOut:
    return DelayPredictionOut(
        bucket_0_15=probabilities.get(BUCKET_LABELS[0], 0.0),
        bucket_16_30=probabilities.get(BUCKET_LABELS[1], 0.0),
        bucket_31_45=probabilities.get(BUCKET_LABELS[2], 0.0),
        bucket_over_45=probabilities.get(BUCKET_LABELS[3], 0.0),
    )


def _invoice_out(rec) -> InvoiceOut:
    return InvoiceOut(
        invoice_id=rec.invoice_id,
        customer_id=rec.customer_id,
        customer_name=rec.customer_name,
        invoice_amount=float(rec.invoice_amount),
        invoice_date="",
        due_date="",
        payment_status="OVERDUE" if rec.days_overdue > 0 else "PENDING",
        days_overdue=rec.days_overdue,
    )


@router.get("/action-queue", response_model=list[ActionQueueItemOut], response_model_by_alias=True)
def action_queue() -> list[ActionQueueItemOut]:
    """The prioritized daily action queue (FR-009)."""
    return [
        ActionQueueItemOut(
            id=f"AQ-{rec.invoice_id}",
            invoice=_invoice_out(rec),
            priority=rec.priority.value,
            recommended_action=rec.recommended_action.value,
            reason=rec.reason,
            approval_state=rec.approval_state.value,
            prediction=_prediction_out(rec.delay_probabilities),
        )
        for rec in build_action_queue()
    ]


@router.get("/summary", response_model=PortfolioSummaryOut, response_model_by_alias=True)
def portfolio_summary() -> PortfolioSummaryOut:
    """Headline figures for the dashboard."""
    queue = build_action_queue()
    forecast = get_cash_forecast()

    total = sum((r.invoice_amount for r in queue), Decimal(0))
    # "At risk" is the value of everything the model expects to run past 45 days.
    at_risk = sum(
        (
            r.invoice_amount
            for r in queue
            if r.delay_probabilities.get(BUCKET_LABELS[3], 0.0) >= 0.4
        ),
        Decimal(0),
    )

    return PortfolioSummaryOut(
        total_receivables=float(total),
        at_risk=float(at_risk),
        open_invoices=len(queue),
        shortfall_amount=(
            float(forecast.shortfall_amount) if forecast.shortfall_amount else None
        ),
        shortfall_date=(
            forecast.shortfall_date.isoformat() if forecast.shortfall_date else None
        ),
    )


@router.get("/forecast", response_model=CashForecastOut, response_model_by_alias=True)
def cash_forecast() -> CashForecastOut:
    """30-day rolling cash forecast with shortfall contributors (FR-004, FR-015)."""
    forecast = get_cash_forecast()
    queue_by_id = {r.invoice_id: r for r in build_action_queue()}

    return CashForecastOut(
        points=[
            ForecastPointOut(date=p.day.isoformat(), projected_cash=float(p.projected_cash))
            for p in forecast.points
        ],
        cash_threshold=float(forecast.cash_threshold),
        shortfall_date=(
            forecast.shortfall_date.isoformat() if forecast.shortfall_date else None
        ),
        shortfall_amount=(
            float(forecast.shortfall_amount) if forecast.shortfall_amount else None
        ),
        contributing_invoices=[
            ContributingInvoiceOut(
                invoice_id=c.invoice_id,
                customer_name=(
                    queue_by_id[c.invoice_id].customer_name
                    if c.invoice_id in queue_by_id
                    else c.customer_id
                ),
                amount=float(c.amount),
                contribution=float(c.contribution),
            )
            for c in forecast.contributors[:5]
        ],
    )


@router.get(
    "/invoice/{invoice_id}", response_model=InvestigationOut, response_model_by_alias=True
)
def investigation(invoice_id: str) -> InvestigationOut:
    """Full investigation detail for one invoice (FR-003, FR-007, FR-014)."""
    data = get_investigation(invoice_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")

    invoice = data["invoice"]
    rec = data["recommendation"]
    if rec is None:
        raise HTTPException(status_code=404, detail="No recommendation for this invoice")

    return InvestigationOut(
        invoice=InvoiceOut(
            invoice_id=invoice.invoice_id,
            customer_id=invoice.customer_id,
            customer_name=rec.customer_name,
            invoice_amount=float(invoice.invoice_amount),
            invoice_date=invoice.invoice_date.isoformat(),
            due_date=invoice.due_date.isoformat(),
            payment_status=invoice.payment_status.value,
            days_overdue=rec.days_overdue,
        ),
        prediction=_prediction_out(rec.delay_probabilities),
        factors=[
            PredictionFactorOut(
                label=f["feature"],
                detail=f["description"],
                # Gain importance is unsigned, so direction is reported as
                # risk-increasing only where the model's own delay signal is
                # elevated. Per-prediction SHAP would give a true sign (#21).
                direction=(
                    "increases_risk"
                    if rec.delay_probabilities.get(BUCKET_LABELS[3], 0.0) >= 0.3
                    else "decreases_risk"
                ),
            )
            for f in data["factors"]
        ],
        rules=RuleFlagsOut(
            statutory_flag=data["msmed"]["statutory_flag"],
            statutory_interest=(
                float(data["statutory_interest"]) if data["statutory_interest"] else None
            ),
            treds_eligible=data["treds"]["eligible"],
            treds_ineligible_reason=(
                None if data["treds"]["eligible"] else data["treds"]["reason"]
            ),
        ),
        # The Receivables Investigator agent (#12) isn't built yet, so findings
        # are reported as empty rather than fabricated. The shape is fixed so
        # the screen doesn't change when the agent lands.
        findings=AgentFindingsOut(
            payment_promise=False,
            promised_date=None,
            dispute_detected=False,
            confidence=0.0,
            evidence=["Communication analysis not yet available"],
        ),
        recommended_action=rec.recommended_action.value,
        reason=rec.reason,
        approval_state=rec.approval_state.value,
        audit_trail=[
            {
                "timestamp": e.timestamp,
                "decidedBy": e.decided_by,
                "what": e.what,
                "why": e.why,
            }
            for e in rec.audit_trail
        ],
    )
