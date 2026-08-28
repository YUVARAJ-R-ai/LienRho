"""API routes backing the four frontend screens."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    ActionQueueItemOut,
    AgentFindingsOut,
    ApprovalResultOut,
    ArtifactOut,
    AuditEntryOut,
    CashForecastOut,
    ContributingInvoiceOut,
    DelayPredictionOut,
    ForecastPointOut,
    InvestigationOut,
    InvoiceOut,
    PortfolioSummaryOut,
    PredictionFactorOut,
    RuleFlagsOut,
    SyncResultOut,
)
from app.db.scoping import Principal, get_current_org_id, get_current_principal
from app.db.session import get_db
from app.decision_engine.engine import ApprovalRequired
from app.decision_engine.service import (
    build_action_queue,
    build_artifact,
    build_draft,
    decide_on_action,
    get_cash_forecast,
    get_findings,
    get_investigation,
)
from app.ml_core.features import BUCKET_LABELS
from app.outreach.dossier import EscalationDossier
from app.outreach.drafts import DraftChannel, ReminderDraft
from app.outreach.treds_submission import TredsIneligible, TredsSubmission

# Auth is declared on the router, not on each endpoint. A dependency listed
# here applies to every route below it including ones added later, so a new
# endpoint cannot quietly ship unauthenticated — the same reasoning that puts
# the approval gate inside each artifact generator rather than once upstream.
router = APIRouter(
    prefix="/api",
    tags=["lienrho"],
    dependencies=[Depends(get_current_principal)],
    responses={401: {"description": "Missing or invalid access token"}},
)


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
def action_queue(org_id: str = Depends(get_current_org_id)) -> list[ActionQueueItemOut]:
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
        for rec in build_action_queue(org_id=org_id)
    ]


@router.get("/summary", response_model=PortfolioSummaryOut, response_model_by_alias=True)
def portfolio_summary(org_id: str = Depends(get_current_org_id)) -> PortfolioSummaryOut:
    """Headline figures for the dashboard."""
    queue = build_action_queue(org_id=org_id)
    forecast = get_cash_forecast(org_id=org_id)

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
def cash_forecast(org_id: str = Depends(get_current_org_id)) -> CashForecastOut:
    """30-day rolling cash forecast with shortfall contributors (FR-004, FR-015)."""
    forecast = get_cash_forecast(org_id=org_id)
    queue_by_id = {r.invoice_id: r for r in build_action_queue(org_id=org_id)}

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
def investigation(
    invoice_id: str, org_id: str = Depends(get_current_org_id)
) -> InvestigationOut:
    """Full investigation detail for one invoice (FR-003, FR-007, FR-014)."""
    data = get_investigation(invoice_id, org_id=org_id)
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
        findings=_findings_out(get_findings(invoice_id, org_id=org_id)),
        recommended_action=rec.recommended_action.value,
        reason=rec.reason,
        approval_state=rec.approval_state.value,
        audit_trail=[
            AuditEntryOut(
                timestamp=e.timestamp,
                decided_by=e.decided_by,
                what=e.what,
                why=e.why,
            )
            for e in rec.audit_trail
        ],
    )


def _artifact_out(artifact) -> ArtifactOut | None:
    """Wrap whichever of the three artifacts was produced (FR-011/012/013)."""
    if artifact is None:
        return None

    if isinstance(artifact, TredsSubmission):
        return ArtifactOut(
            kind="TREDS_SUBMISSION",
            title=f"Mock TReDS submission — {artifact.payload.invoice_id}",
            content_markdown=artifact.to_markdown(),
            # The only artifact with a machine-readable body: a financier's
            # intake would consume this, whereas a reminder and a dossier are
            # read by people.
            payload=artifact.payload.model_dump(mode="json"),
        )

    if isinstance(artifact, EscalationDossier):
        return ArtifactOut(
            kind="DOSSIER",
            title=f"Statutory escalation dossier — {artifact.invoice_id}",
            content_markdown=artifact.to_markdown(),
        )

    if isinstance(artifact, ReminderDraft):
        return ArtifactOut(
            kind="REMINDER",
            title=artifact.subject or f"Reminder — {artifact.invoice_id}",
            content_markdown=artifact.to_markdown(),
            editable=artifact.editable,
        )

    return None


@router.get("/invoice/{invoice_id}/draft", response_model=ArtifactOut)
def invoice_draft(
    invoice_id: str,
    channel: DraftChannel = DraftChannel.EMAIL,
    org_id: str = Depends(get_current_org_id),
) -> ArtifactOut:
    """Draft a reminder for one invoice (FR-011).

    Not gated on approval — the draft is what the user reads in order to decide.
    Sending it is their own action in their own client (OQ-01).
    """
    draft = build_draft(invoice_id, channel=channel, org_id=org_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")

    out = _artifact_out(draft)
    assert out is not None  # a ReminderDraft always maps
    return out


@router.get("/invoice/{invoice_id}/artifact", response_model=ArtifactOut)
def invoice_artifact(
    invoice_id: str, org_id: str = Depends(get_current_org_id)
) -> ArtifactOut:
    """Re-fetch the artifact an approved action produced (FR-011/012/013).

    Without this, an approved dossier would exist only in the browser tab that
    approved it and vanish on reload — which is exactly the wrong property for a
    document someone intends to file.

    Still gated: `build_artifact` raises `ApprovalRequired` for anything not
    approved, so this is a way to re-read a decision, not to bypass one.
    """
    recommendation = next(
        (r for r in build_action_queue(org_id=org_id) if r.invoice_id == invoice_id), None
    )
    if recommendation is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")

    try:
        artifact = _artifact_out(build_artifact(recommendation, org_id=org_id))
    except ApprovalRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TredsIneligible as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{invoice_id} is not TReDS-eligible",
                "failingConditions": exc.failing_conditions,
            },
        ) from exc

    if artifact is None:
        raise HTTPException(status_code=404, detail="No artifact for this action")
    return artifact


def _decide(
    invoice_id: str, *, approved: bool, actor: str, org_id: str
) -> ApprovalResultOut:
    """Shared body for approve and reject (FR-010, BR-APPROVAL)."""
    recommendation = decide_on_action(
        invoice_id, approved=approved, actor=actor, org_id=org_id
    )
    if recommendation is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")

    artifact = None
    if approved:
        try:
            artifact = _artifact_out(build_artifact(recommendation, org_id=org_id))
        except TredsIneligible as exc:
            # The approval itself stands — the user decided, and that decision is
            # recorded. What failed is the submission, and saying which condition
            # failed is more useful than a bare 500.
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"{invoice_id} is not TReDS-eligible",
                    "failingConditions": exc.failing_conditions,
                },
            ) from exc

    return ApprovalResultOut(
        invoice_id=recommendation.invoice_id,
        approval_state=recommendation.approval_state.value,
        recommended_action=recommendation.recommended_action.value,
        artifact=artifact,
        audit_trail=[
            AuditEntryOut(
                timestamp=e.timestamp, decided_by=e.decided_by, what=e.what, why=e.why
            )
            for e in recommendation.audit_trail
        ],
    )


@router.post("/actions/{invoice_id}/approve", response_model=ApprovalResultOut)
def approve_action(
    invoice_id: str, principal: Principal = Depends(get_current_principal)
) -> ApprovalResultOut:
    """Approve a recommendation and generate what it produces (FR-010, FR-012, FR-013).

    `actor` comes from the verified token, never from the request. FR-014 asks
    who decided; a caller-supplied name would let anyone sign the audit trail
    with somebody else's identity, which is the one thing that record exists to
    prevent.
    """
    return _decide(
        invoice_id, approved=True, actor=principal.email, org_id=principal.org_id
    )


@router.post("/actions/{invoice_id}/reject", response_model=ApprovalResultOut)
def reject_action(
    invoice_id: str, principal: Principal = Depends(get_current_principal)
) -> ApprovalResultOut:
    """Reject a recommendation. Invoice state is left unchanged (FR-010 AC-2)."""
    return _decide(
        invoice_id, approved=False, actor=principal.email, org_id=principal.org_id
    )


def _findings_out(findings) -> AgentFindingsOut:
    """Render Investigator findings for the UI (FR-007).

    Promise credibility is folded into the evidence list rather than hidden: a
    promise from a customer who has broken three is the single most useful thing
    on the screen, and burying it would defeat the point of reading the threads.
    """
    if findings is None:
        return AgentFindingsOut(
            payment_promise=False,
            promised_date=None,
            dispute_detected=False,
            confidence=0.0,
            evidence=["No correspondence on file for this invoice"],
        )

    evidence = list(findings.evidence)
    if findings.payment_promise and not findings.promise_is_credible:
        kept_share = (
            f" (kept {findings.promise_reliability:.0%} of past promises)"
            if findings.promise_reliability is not None
            else ""
        )
        evidence.insert(
            0,
            f"Promise treated as unreliable — {findings.prior_broken_promises} prior "
            f"promise(s) not kept{kept_share}",
        )

    return AgentFindingsOut(
        payment_promise=findings.payment_promise,
        promised_date=findings.promised_date.isoformat() if findings.promised_date else None,
        dispute_detected=findings.dispute_detected,
        confidence=findings.confidence,
        evidence=evidence,
    )


# --------------------------------------------------------------- sync (FR-001)


def _sync_out(result) -> SyncResultOut:
    return SyncResultOut(
        source=result.source,
        status=result.status,
        started_at=result.started_at.isoformat(),
        finished_at=result.finished_at.isoformat() if result.finished_at else None,
        customers_synced=result.customers_synced,
        invoices_synced=result.invoices_synced,
        payments_synced=result.payments_synced,
        error=result.error,
    )


@router.post("/sync", response_model=SyncResultOut, response_model_by_alias=True)
def run_sync(
    org_id: str = Depends(get_current_org_id), db: Session = Depends(get_db)
) -> SyncResultOut:
    """Pull this org's book from the configured connector into the canonical
    store (FR-001, on-demand half).

    Returns 200 with `status: "FAILED"` rather than a 5xx when the connector is
    unreachable. The request itself succeeded — the sync is what failed, and
    that outcome is a recorded fact the caller needs to read, not an error to
    be swallowed by a generic handler. The previous portfolio is untouched
    (AC-2).
    """
    from app.config import settings
    from app.connectors import get_connector
    from app.sync import sync_portfolio

    source = settings.sync_connector
    try:
        connector = get_connector(source)
    except (RuntimeError, ValueError) as exc:
        # Misconfiguration, not a sync failure: there is nothing to attempt.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _sync_out(sync_portfolio(db, org_id=org_id, connector=connector, source=source))


@router.get("/sync", response_model=SyncResultOut | None, response_model_by_alias=True)
def sync_status(
    org_id: str = Depends(get_current_org_id), db: Session = Depends(get_db)
) -> SyncResultOut | None:
    """The most recent sync for this org, successful or not.

    Null when none has ever run. Without this, "the queue is empty" and "we
    have never managed to read the book" are indistinguishable from the
    outside, and the second is an outage reading as good news.
    """
    from app.sync import last_sync

    result = last_sync(db, org_id=org_id)
    return _sync_out(result) if result else None
