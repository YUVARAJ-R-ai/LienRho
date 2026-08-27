"""API response shapes.

These mirror `frontend/src/lib/types.ts`. The two are maintained by hand today —
issue #21 tracks generating one from the other, which is what will actually keep
them honest.

Field names are camelCase to match the frontend's convention, so responses drop
straight into the existing components without a translation layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InvoiceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    invoice_id: str = Field(serialization_alias="invoiceId")
    customer_id: str = Field(serialization_alias="customerId")
    customer_name: str = Field(serialization_alias="customerName")
    invoice_amount: float = Field(serialization_alias="invoiceAmount")
    invoice_date: str = Field(serialization_alias="invoiceDate")
    due_date: str = Field(serialization_alias="dueDate")
    payment_status: str = Field(serialization_alias="paymentStatus")
    days_overdue: int = Field(serialization_alias="daysOverdue")


class DelayPredictionOut(BaseModel):
    bucket_0_15: float
    bucket_16_30: float
    bucket_31_45: float
    bucket_over_45: float


class ActionQueueItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    invoice: InvoiceOut
    priority: str
    recommended_action: str = Field(serialization_alias="recommendedAction")
    reason: str
    approval_state: str = Field(serialization_alias="approvalState")
    prediction: DelayPredictionOut


class PredictionFactorOut(BaseModel):
    label: str
    detail: str
    direction: str


class RuleFlagsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    statutory_flag: bool = Field(serialization_alias="statutoryFlag")
    statutory_interest: float | None = Field(serialization_alias="statutoryInterest")
    treds_eligible: bool = Field(serialization_alias="tredsEligible")
    treds_ineligible_reason: str | None = Field(serialization_alias="tredsIneligibleReason")


class AgentFindingsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payment_promise: bool = Field(serialization_alias="paymentPromise")
    promised_date: str | None = Field(serialization_alias="promisedDate")
    dispute_detected: bool = Field(serialization_alias="disputeDetected")
    confidence: float
    evidence: list[str]


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timestamp: str
    decided_by: str = Field(serialization_alias="decidedBy")
    what: str
    why: str


class InvestigationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    invoice: InvoiceOut
    prediction: DelayPredictionOut
    factors: list[PredictionFactorOut]
    rules: RuleFlagsOut
    findings: AgentFindingsOut
    recommended_action: str = Field(serialization_alias="recommendedAction")
    reason: str
    approval_state: str = Field(serialization_alias="approvalState")
    audit_trail: list[AuditEntryOut] = Field(serialization_alias="auditTrail")


class ForecastPointOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    projected_cash: float = Field(serialization_alias="projectedCash")


class ContributingInvoiceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    invoice_id: str = Field(serialization_alias="invoiceId")
    customer_name: str = Field(serialization_alias="customerName")
    amount: float
    contribution: float


class CashForecastOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    points: list[ForecastPointOut]
    cash_threshold: float = Field(serialization_alias="cashThreshold")
    shortfall_date: str | None = Field(serialization_alias="shortfallDate")
    shortfall_amount: float | None = Field(serialization_alias="shortfallAmount")
    contributing_invoices: list[ContributingInvoiceOut] = Field(
        serialization_alias="contributingInvoices"
    )


class ArtifactOut(BaseModel):
    """A generated execution artifact (FR-011, FR-012, FR-013).

    One shape for all three: the screen renders `contentMarkdown` and does not
    need to know whether it is holding a reminder, a financing submission, or a
    legal filing. `payload` carries the machine-readable TReDS body, which is
    the only one of the three that a downstream system would ever consume.
    """

    model_config = ConfigDict(populate_by_name=True)

    kind: str  # REMINDER | TREDS_SUBMISSION | DOSSIER
    title: str
    content_markdown: str = Field(serialization_alias="contentMarkdown")
    payload: dict | None = None
    editable: bool = False


class ApprovalResultOut(BaseModel):
    """The outcome of a human decision, with whatever it produced (FR-010)."""

    model_config = ConfigDict(populate_by_name=True)

    invoice_id: str = Field(serialization_alias="invoiceId")
    approval_state: str = Field(serialization_alias="approvalState")
    recommended_action: str = Field(serialization_alias="recommendedAction")
    # Null on rejection — refusing an action must not hand back the artifact it
    # would have produced (FR-010 AC-2).
    artifact: ArtifactOut | None = None
    audit_trail: list[AuditEntryOut] = Field(serialization_alias="auditTrail")


class PortfolioSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_receivables: float = Field(serialization_alias="totalReceivables")
    at_risk: float = Field(serialization_alias="atRisk")
    open_invoices: int = Field(serialization_alias="openInvoices")
    shortfall_amount: float | None = Field(serialization_alias="shortfallAmount")
    shortfall_date: str | None = Field(serialization_alias="shortfallDate")


class SyncResultOut(BaseModel):
    """One connector sync, successful or not (FR-001 AC-2)."""

    model_config = ConfigDict(populate_by_name=True)

    source: str
    status: str
    started_at: str = Field(alias="startedAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    customers_synced: int = Field(default=0, alias="customersSynced")
    invoices_synced: int = Field(default=0, alias="invoicesSynced")
    payments_synced: int = Field(default=0, alias="paymentsSynced")
    error: str | None = None
