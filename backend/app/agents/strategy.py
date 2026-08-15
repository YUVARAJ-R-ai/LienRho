"""Recovery Strategy agent (FR-008, issue #13).

Selects Track A/B/C for one invoice and explains why.

The architectural point of this module is what it *doesn't* do: it never
computes a statutory threshold, an interest figure, or an eligibility verdict.
Those arrive through `ToolBox`, which records every call. What the agent
contributes is judgement over the results — weighing a statutory breach against
a credible promise against a cash shortfall — and that judgement is the part a
language model can legitimately own (ADR-002).

Same two-implementation pattern as the Investigator: `RuleBasedStrategist` runs
today and stays as the fallback; `LLMStrategist` is unblocked by `OQ-02`. Both
call the same tools and return the same validated `StrategyRecommendation`, so
the tool-call trace looks identical either way — which is exactly why the trace
is meaningful evidence rather than decoration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.agents.schemas import InvestigatorFindings, StrategyRecommendation
from app.agents.tools import ToolBox

# RBI bank rate applicable to the demo period. A real deployment reads the rate
# notified for the period being claimed rather than a constant.
DEMO_RBI_BANK_RATE = Decimal("0.065")

# Indicative discounting rate for the mock TReDS simulation.
DEMO_DISCOUNT_RATE = Decimal("0.12")


@dataclass
class StrategyContext:
    """Everything the strategist may consider for one invoice."""

    invoice_id: str
    invoice_amount: Decimal
    due_date: date
    invoice_date: date
    acceptance_date: date
    buyer_participates_in_treds: bool
    probability_over_45: float
    shortfall_projected: bool
    contributes_to_shortfall: bool
    findings: InvestigatorFindings | None = None

    @property
    def agreed_credit_days(self) -> int:
        return (self.due_date - self.invoice_date).days


@dataclass
class StrategyResult:
    """The recommendation plus the evidence trail behind it."""

    recommendation: StrategyRecommendation
    toolbox: ToolBox
    statutory_flag: bool
    statutory_interest: Decimal | None
    treds_eligible: bool
    treds_reason: str

    @property
    def trace(self) -> list[str]:
        return self.toolbox.trace


class Strategist(ABC):
    @abstractmethod
    def recommend(self, context: StrategyContext, *, as_of: date) -> StrategyResult: ...


class RuleBasedStrategist(Strategist):
    """Deterministic strategy selection over tool results.

    Gathers facts through the ToolBox exactly as the LLM implementation will,
    so the resulting trace is the same shape and the fallback is a genuine
    substitute rather than a different code path.
    """

    def recommend(self, context: StrategyContext, *, as_of: date) -> StrategyResult:
        tools = ToolBox(as_of=as_of)

        # 1. Statutory position — always checked, since it outranks everything.
        msmed = tools.msmed_threshold(
            acceptance_date=context.acceptance_date,
            agreed_credit_days=context.agreed_credit_days,
        )
        statutory_flag = bool(msmed["statutory_flag"])

        # 2. Interest, only where a breach exists. Calling it otherwise would put
        #    a meaningless figure in the trace.
        statutory_interest = None
        if statutory_flag:
            statutory_interest = tools.statutory_interest(
                principal=context.invoice_amount,
                acceptance_date=context.acceptance_date,
                agreed_credit_days=context.agreed_credit_days,
                rbi_bank_rate=DEMO_RBI_BANK_RATE,
            )

        # 3. Financing position.
        treds = tools.treds_eligibility(
            invoice_amount=context.invoice_amount,
            due_date=context.due_date,
            invoice_is_buyer_approved=True,
            buyer_participates_in_treds=context.buyer_participates_in_treds,
        )
        treds_eligible = bool(treds["eligible"])

        if treds_eligible and context.shortfall_projected:
            tools.financing_terms(
                invoice_amount=context.invoice_amount,
                due_date=context.due_date,
                annual_discount_rate=DEMO_DISCOUNT_RATE,
            )

        recommendation = self._select(
            context=context,
            statutory_flag=statutory_flag,
            statutory_interest=statutory_interest,
            treds_eligible=treds_eligible,
        )

        return StrategyResult(
            recommendation=recommendation,
            toolbox=tools,
            statutory_flag=statutory_flag,
            statutory_interest=statutory_interest,
            treds_eligible=treds_eligible,
            treds_reason=str(treds["reason"]),
        )

    def _select(
        self,
        *,
        context: StrategyContext,
        statutory_flag: bool,
        statutory_interest: Decimal | None,
        treds_eligible: bool,
    ) -> StrategyRecommendation:
        findings = context.findings
        promise = bool(findings and findings.payment_promise)
        credible = bool(findings and findings.promise_is_credible)
        dispute = bool(findings and findings.dispute_detected)

        factors: list[str] = []

        if dispute:
            factors.append(
                findings.dispute_summary if findings else "Dispute on record"
            )
            return StrategyRecommendation(
                action="FOLLOW_UP",
                reason=(
                    "A dispute is on record — it must be resolved by a human before "
                    "escalation or financing is appropriate"
                ),
                deciding_factors=factors,
                confidence=0.9,
            )

        if statutory_flag:
            factors.append("MSMED statutory threshold crossed")
            if statutory_interest is not None:
                factors.append(f"Statutory interest accrued: Rs {statutory_interest:,.2f}")
            if promise and not credible:
                factors.append(
                    f"{findings.prior_broken_promises} prior promise(s) not kept"
                    if findings
                    else "Prior promises not kept"
                )
                return StrategyRecommendation(
                    action="ESCALATE",
                    reason=(
                        "Statutory threshold crossed and the customer's latest "
                        "assurance follows a pattern of broken promises"
                    ),
                    deciding_factors=factors,
                    confidence=0.88,
                )
            return StrategyRecommendation(
                action="ESCALATE",
                reason="Statutory threshold crossed with no credible payment commitment",
                deciding_factors=factors,
                confidence=0.85,
            )

        if treds_eligible and context.shortfall_projected:
            factors.append("TReDS eligible")
            factors.append("Cash shortfall projected within the forecast horizon")
            return StrategyRecommendation(
                action="FINANCE",
                reason=(
                    "TReDS eligible and discounting it would close the projected "
                    "cash shortfall"
                ),
                deciding_factors=factors,
                confidence=0.8,
            )

        if promise and credible:
            when = (
                f" for {findings.promised_date}"
                if findings and findings.promised_date
                else ""
            )
            factors.append(f"Credible payment promise{when}")
            if findings and findings.promise_reliability is not None:
                factors.append(
                    f"Customer has kept {findings.promise_reliability:.0%} of past promises"
                )
            return StrategyRecommendation(
                action="FOLLOW_UP",
                reason="A credible promise is on record — a reminder should suffice",
                deciding_factors=factors,
                confidence=0.82,
            )

        if context.probability_over_45 >= 0.5:
            factors.append(
                f"{context.probability_over_45:.0%} predicted probability of >45 day delay"
            )
            return StrategyRecommendation(
                action="FOLLOW_UP",
                reason="High predicted delay risk with no commitment on record",
                deciding_factors=factors,
                confidence=0.75,
            )

        factors.append("No statutory breach, dispute, or elevated delay risk")
        return StrategyRecommendation(
            action="FOLLOW_UP",
            reason="Routine follow-up",
            deciding_factors=factors,
            confidence=0.7,
        )


class LLMStrategist(Strategist):
    """LangGraph/LLM implementation — blocked on OQ-02.

    Intended shape: a LangGraph graph with a single agent node bound to
    `TOOL_SCHEMAS`, looping until the model stops requesting tools, then
    emitting a structured `StrategyRecommendation`.

    Two rules the implementation must hold to:

    1. **Never accept a statutory or financial figure from the model.** If the
       recommendation text contains a number, it has to be one a tool returned.
       The `ToolBox` record is what makes that checkable.
    2. **Fall through to `RuleBasedStrategist` on any failure** — refusal,
       malformed output, timeout, rate limit. A degraded recommendation is
       recoverable; a failed action queue is not.
    """

    def __init__(self, fallback: Strategist | None = None):
        self._fallback = fallback or RuleBasedStrategist()

    def recommend(self, context: StrategyContext, *, as_of: date) -> StrategyResult:
        raise NotImplementedError(
            "LLM provider not selected — see OQ-02. Use RuleBasedStrategist."
        )


def get_strategist() -> Strategist:
    """The strategist the application should use.

    Returns the deterministic implementation while OQ-02 is open. Switching is a
    one-line change once a provider and key exist.
    """
    return RuleBasedStrategist()
