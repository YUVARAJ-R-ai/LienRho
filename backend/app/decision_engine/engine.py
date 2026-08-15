"""Action prioritization and the approval gate (FR-009, FR-010, CON-06).

This is where ML output, deterministic rule flags, and (later) agent findings
combine into the single ranked list the user acts on each morning.

Two things are load-bearing:

1. **Nothing sensitive executes without a human.** Every recommendation is born
   PENDING_APPROVAL. Only an explicit user decision moves it, and rejecting
   must leave invoice state untouched (BR-APPROVAL, FR-010).
2. **Every recommendation carries its reasoning.** NFR-007 requires tracing an
   action back to the specific prediction and rule evaluation behind it without
   reading raw logs, so the audit trail is built here rather than bolted on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum


class RecommendedAction(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    FINANCE = "FINANCE"
    ESCALATE = "ESCALATE"


class Priority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    FOLLOW_UP = "FOLLOW_UP"


class ApprovalState(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Actions that change money or legal standing need explicit sign-off (CON-06).
SENSITIVE_ACTIONS = {RecommendedAction.FINANCE, RecommendedAction.ESCALATE}


class ApprovalRequired(Exception):
    """Raised when execution is attempted on an unapproved sensitive action."""


@dataclass
class AuditEntry:
    """FR-014: what, why, who decided, when."""

    timestamp: str
    decided_by: str  # ML | RULES | AGENT | HUMAN
    what: str
    why: str


@dataclass
class ActionRecommendation:
    invoice_id: str
    customer_id: str
    customer_name: str
    invoice_amount: Decimal
    days_overdue: int
    priority: Priority
    recommended_action: RecommendedAction
    reason: str
    approval_state: ApprovalState = ApprovalState.PENDING_APPROVAL
    delay_probabilities: dict[str, float] = field(default_factory=dict)
    audit_trail: list[AuditEntry] = field(default_factory=list)
    # Ranking inputs, retained so the ordering is inspectable rather than opaque.
    priority_score: float = 0.0

    @property
    def requires_approval(self) -> bool:
        return self.recommended_action in SENSITIVE_ACTIONS


def _now() -> str:
    return datetime.now(UTC).isoformat()


def decide_action(
    *,
    statutory_flag: bool,
    treds_eligible: bool,
    probability_over_45: float,
    contributes_to_shortfall: bool,
    shortfall_projected: bool = False,
    payment_promise: bool = False,
    promise_is_credible: bool = True,
    dispute_detected: bool = False,
) -> tuple[RecommendedAction, str]:
    """Choose Track A/B/C for one invoice (FR-008, prd.md §14).

    Ordering matters. A statutory breach outranks financing because the legal
    clock is already running.

    Financing keys off whether the business *has* a projected shortfall, not
    whether this invoice caused it. An invoice likely to be paid on time is the
    best discounting candidate — low risk to the financier, cash in hand now —
    whereas the invoice driving the shortfall is usually the one nobody will
    finance. Requiring the invoice to be the cause had it backwards.

    Discounting still isn't free, so with no shortfall projected a reminder wins.

    A promise only softens the recommendation when it is *credible*. A customer
    who has broken three prior promises making a fourth is evidence of a
    pattern, not of intent to pay — treating those alike is exactly the mistake
    the Investigator exists to prevent.
    """
    if dispute_detected:
        # A disputed invoice must not be escalated or financed - the underlying
        # disagreement has to be resolved by a human first.
        return (
            RecommendedAction.FOLLOW_UP,
            "Dispute detected — resolve the disagreement before escalating or financing",
        )

    if statutory_flag:
        if payment_promise and not promise_is_credible:
            return (
                RecommendedAction.ESCALATE,
                (
                    "MSMED statutory threshold crossed; the customer has promised "
                    "before and not paid, so the latest assurance does not justify "
                    "waiting (Track C)"
                ),
            )
        return (
            RecommendedAction.ESCALATE,
            "MSMED statutory threshold crossed with no payment promise on record (Track C)",
        )

    if treds_eligible and shortfall_projected:
        return (
            RecommendedAction.FINANCE,
            "TReDS eligible and can be discounted to close the projected cash shortfall (Track B)",
        )

    if payment_promise and promise_is_credible:
        return (
            RecommendedAction.FOLLOW_UP,
            "Payment promised and no dispute on record — a reminder should suffice (Track A)",
        )

    if probability_over_45 >= 0.5:
        return (
            RecommendedAction.FOLLOW_UP,
            f"High predicted delay risk ({probability_over_45:.0%} chance of >45 days) (Track A)",
        )

    return (RecommendedAction.FOLLOW_UP, "Routine follow-up (Track A)")


def score_priority(
    *,
    invoice_amount: Decimal,
    days_overdue: int,
    probability_over_45: float,
    statutory_flag: bool,
    contributes_to_shortfall: bool,
    portfolio_max_amount: Decimal,
) -> float:
    """Blend FR-009's six ranking inputs into one comparable score.

    Value is normalised against the largest open invoice so the weighting holds
    for any portfolio size rather than assuming rupee magnitudes.
    """
    value_weight = float(invoice_amount) / max(float(portfolio_max_amount), 1.0)
    overdue_weight = min(days_overdue / 60.0, 1.0)

    score = (
        0.30 * probability_over_45
        + 0.25 * value_weight
        + 0.20 * overdue_weight
        + 0.15 * (1.0 if statutory_flag else 0.0)
        + 0.10 * (1.0 if contributes_to_shortfall else 0.0)
    )
    return round(score, 4)


def assign_priority(
    *,
    score: float,
    statutory_flag: bool,
    contributes_to_shortfall: bool,
) -> Priority:
    """Bucket a scored action into the queue's three tiers (prd.md §16).

    Statutory breaches and shortfall drivers are always Critical regardless of
    score - both have a deadline the user cannot negotiate.
    """
    if statutory_flag or contributes_to_shortfall:
        return Priority.CRITICAL
    if score >= 0.45:
        return Priority.HIGH
    return Priority.FOLLOW_UP


def build_recommendation(
    *,
    invoice,
    customer_name: str,
    as_of: date,
    delay_probabilities: dict[str, float],
    probability_over_45: float,
    statutory_flag: bool,
    statutory_reason: str,
    treds_eligible: bool,
    treds_reason: str,
    contributes_to_shortfall: bool,
    portfolio_max_amount: Decimal,
    shortfall_projected: bool = False,
    payment_promise: bool = False,
    promise_is_credible: bool = True,
    dispute_detected: bool = False,
    findings_summary: str | None = None,
    tool_trace: list[str] | None = None,
) -> ActionRecommendation:
    """Assemble one queue item, including the audit trail behind it."""
    days_overdue = max((as_of - invoice.due_date).days, 0)

    action, reason = decide_action(
        statutory_flag=statutory_flag,
        treds_eligible=treds_eligible,
        probability_over_45=probability_over_45,
        contributes_to_shortfall=contributes_to_shortfall,
        shortfall_projected=shortfall_projected,
        payment_promise=payment_promise,
        promise_is_credible=promise_is_credible,
        dispute_detected=dispute_detected,
    )
    score = score_priority(
        invoice_amount=invoice.invoice_amount,
        days_overdue=days_overdue,
        probability_over_45=probability_over_45,
        statutory_flag=statutory_flag,
        contributes_to_shortfall=contributes_to_shortfall,
        portfolio_max_amount=portfolio_max_amount,
    )
    priority = assign_priority(
        score=score,
        statutory_flag=statutory_flag,
        contributes_to_shortfall=contributes_to_shortfall,
    )

    timestamp = _now()
    audit = [
        AuditEntry(
            timestamp=timestamp,
            decided_by="ML",
            what=f"Predicted {probability_over_45:.0%} probability of >45 day delay",
            why="XGBoost delay model over invoice, customer history, and seasonality features",
        ),
        AuditEntry(
            timestamp=timestamp,
            decided_by="RULES",
            what=f"statutory_flag={statutory_flag}, treds_eligible={treds_eligible}",
            why=(
                f"check_msmed_threshold(): {statutory_reason}; "
                f"check_treds_eligibility(): {treds_reason}"
            ),
        ),
        # One entry per deterministic function the agent called. This is what
        # makes ADR-002 inspectable rather than merely asserted: every figure in
        # the recommendation above traces to a named function and its arguments.
        *(
            AuditEntry(
                timestamp=timestamp,
                decided_by="TOOL",
                what=call,
                why="Called by the Recovery Strategy agent — deterministic, not model-generated",
            )
            for call in (tool_trace or [])
        ),
        AuditEntry(
            timestamp=timestamp,
            decided_by="AGENT",
            what=(
                findings_summary
                or "No communication evidence available"
            ),
            why="Receivables Investigator read the customer correspondence",
        ),
        AuditEntry(
            timestamp=timestamp,
            decided_by="AGENT",
            what=f"Recommended {action.value}",
            why=reason,
        ),
    ]

    return ActionRecommendation(
        invoice_id=invoice.invoice_id,
        customer_id=invoice.customer_id,
        customer_name=customer_name,
        invoice_amount=invoice.invoice_amount,
        days_overdue=days_overdue,
        priority=priority,
        recommended_action=action,
        reason=reason,
        delay_probabilities=delay_probabilities,
        audit_trail=audit,
        priority_score=score,
    )


def rank_queue(recommendations: list[ActionRecommendation]) -> list[ActionRecommendation]:
    """Order the queue: tier first, then invoice value within tier (FR-009 AC)."""
    tier_order = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.FOLLOW_UP: 2}
    return sorted(
        recommendations,
        key=lambda r: (tier_order[r.priority], -float(r.invoice_amount)),
    )


def approve(recommendation: ActionRecommendation, *, actor: str) -> ActionRecommendation:
    """Record explicit human approval (FR-010)."""
    recommendation.approval_state = ApprovalState.APPROVED
    recommendation.audit_trail.append(
        AuditEntry(
            timestamp=_now(),
            decided_by="HUMAN",
            what=f"Approved {recommendation.recommended_action.value}",
            why=f"Approved by {actor}",
        )
    )
    return recommendation


def reject(recommendation: ActionRecommendation, *, actor: str) -> ActionRecommendation:
    """Record rejection. Invoice state is deliberately left untouched (FR-010 AC-2)."""
    recommendation.approval_state = ApprovalState.REJECTED
    recommendation.audit_trail.append(
        AuditEntry(
            timestamp=_now(),
            decided_by="HUMAN",
            what=f"Rejected {recommendation.recommended_action.value}",
            why=f"Rejected by {actor} — invoice state unchanged",
        )
    )
    return recommendation


def assert_executable(recommendation: ActionRecommendation) -> None:
    """Gate before any outreach send, TReDS submission, or dossier finalisation.

    Callers must run this immediately before executing. It's a function rather
    than a convention so the gate can't be forgotten silently.
    """
    if (
        recommendation.requires_approval
        and recommendation.approval_state is not ApprovalState.APPROVED
    ):
        raise ApprovalRequired(
            f"{recommendation.recommended_action.value} on {recommendation.invoice_id} "
            f"is {recommendation.approval_state.value}; explicit approval is required (FR-010)"
        )
