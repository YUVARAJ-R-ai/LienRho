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

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from app.agents.llm_client import (
    FRONTIER_TIER,
    LiteLLMChatModel,
    LiteLLMClient,
    LLMClient,
    get_langfuse_handler,
)
from app.agents.schemas import InvestigatorFindings, StrategyRecommendation
from app.agents.tools import ToolBox, build_toolbox_tools

logger = logging.getLogger(__name__)

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
    fallback_reason: str | None = None

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


# ---- LLMStrategist ---------------------------------------------------------


class LLMStrategist(Strategist):
    """LangGraph/LLM implementation (OQ-02, issue #13).

    A stock ReAct agent built with the framework's `create_agent`: the model is
    the `LiteLLMChatModel` adapter, and the tools are `ToolBox` methods exposed
    as `StructuredTool`s by `build_toolbox_tools`. Tool execution still goes
    through `ToolBox`, so the trace is byte-identical in shape to the rule-based
    path — which is why the fallback is a genuine substitute rather than a
    different code path.

    Two rules the implementation holds to:

    1. **Never accept a statutory or financial figure from the model.** The
       model only learns those numbers by calling a tool; if it emits a
       recommendation for a path whose required facts were never gathered, the
       run falls through rather than trusting the text.
    2. **Fall through to `RuleBasedStrategist` on any failure** — refusal,
       malformed output, timeout, rate limit, runaway loop, or a hallucinated
       number. A degraded recommendation is recoverable; a failed action queue
       is not.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        fallback: Strategist | None = None,
    ):
        from app.config import settings

        self._client = client or _gateway_client()
        self._fallback = fallback or RuleBasedStrategist()
        self._max_steps = settings.llm_max_steps

    def recommend(self, context: StrategyContext, *, as_of: date) -> StrategyResult:
        tools = ToolBox(as_of=as_of)
        model = LiteLLMChatModel(client=self._client, model_tier=FRONTIER_TIER)
        graph = create_agent(
            model,
            tools=build_toolbox_tools(tools),
            system_prompt=self._system_prompt(),
        )

        thread_id = f"strategy-{context.invoice_id}-{as_of.isoformat()}"
        handler = get_langfuse_handler()
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "invoice_id": context.invoice_id,
                "as_of": as_of.isoformat(),
                "agent": "strategy",
            },
            # The framework counts node executions, not agent turns: each tool
            # loop is two nodes (agent + tools). Give it headroom past the turn
            # cap without unbinding it, and fall through on GraphRecursionError.
            "recursion_limit": self._max_steps * 3 + 10,
        }
        if handler is not None:
            config["callbacks"] = [handler]

        try:
            final = graph.invoke(
                {"messages": [HumanMessage(self._user_message(context, as_of))]},
                config=config,
            )
        except GraphRecursionError:
            return self._fallback_with(
                context, as_of, f"runaway loop past {self._max_steps} steps"
            )
        except Exception as exc:  # noqa: BLE001 - any gateway failure degrades
            return self._fallback_with(context, as_of, f"LLM call failed: {exc}")

        last = final["messages"][-1]
        try:
            recommendation = self._parse_recommendation(last.content or "")
        except Exception as exc:  # noqa: BLE001 - unparseable is a fallback
            return self._fallback_with(context, as_of, f"unparseable recommendation: {exc}")

        # Rule 1 enforcement: the track must be grounded in the facts it
        # needs, and those facts must have been gathered through a tool.
        missing = self._facts_missing(recommendation, tools)
        if missing:
            return self._fallback_with(
                context, as_of, f"recommendation cites facts never gathered: {missing}"
            )

        return StrategyResult(
            recommendation=recommendation,
            toolbox=tools,
            statutory_flag=_tool_flag(tools, "check_msmed_threshold", "statutory_flag", False),
            statutory_interest=_tool_interest(tools),
            treds_eligible=_tool_flag(tools, "check_treds_eligibility", "eligible", False),
            treds_reason=_tool_reason(tools, "check_treds_eligibility"),
        )

    def _fallback_with(self, context: StrategyContext, as_of: date, reason: str) -> StrategyResult:
        logger.warning("LLMStrategist falling back to rule-based: %s", reason)
        result = self._fallback.recommend(context, as_of=as_of)
        return replace(result, fallback_reason=reason)

    def _system_prompt(self) -> str:
        return (
            "You select the recovery track for ONE invoice: FOLLOW_UP, "
            "FINANCE, or ESCALATE.\n\n"
            "RULES (these are legal and financial, not stylistic):\n"
            "1. NEVER compute a statutory threshold, interest figure, or "
            "TReDS eligibility yourself. Call the provided tools — they "
            "return authoritative values you must quote exactly.\n"
            "2. A dispute on record blocks escalation and financing until "
            "a human resolves it — recommend FOLLOW_UP.\n"
            "3. A statutory breach (check_msmed_threshold -> "
            "statutory_flag=true) outranks everything: ESCALATE, unless "
            "there is a credible payment promise.\n"
            "4. Financing (FINANCE) is only appropriate when the invoice "
            "is TReDS-eligible AND a cash shortfall is projected.\n"
            "5. With no breach, no dispute, and no financing case, a "
            "credible promise or routine risk decides: FOLLOW_UP.\n\n"
            "Gather the facts you need with tools, then reply with ONLY a "
            "JSON object: {\"action\": \"FOLLOW_UP|FINANCE|ESCALATE\", "
            "\"reason\": \"one readable sentence\", "
            "\"deciding_factors\": [\"facts that drove the choice\"], "
            "\"confidence\": 0.0-1.0}. Never put a figure in the JSON "
            "that a tool did not return."
        )

    def _user_message(self, context: StrategyContext, as_of: date) -> str:
        return (
            f"Invoice {context.invoice_id}, as of {as_of.isoformat()}.\n"
            f"amount: {context.invoice_amount}\n"
            f"invoice_date: {context.invoice_date.isoformat()}\n"
            f"due_date: {context.due_date.isoformat()}\n"
            f"acceptance_date: {context.acceptance_date.isoformat()}\n"
            f"agreed_credit_days: {context.agreed_credit_days}\n"
            f"buyer_participates_in_treds: {context.buyer_participates_in_treds}\n"
            f"probability_over_45: {context.probability_over_45:.2f}\n"
            f"shortfall_projected: {context.shortfall_projected}\n"
            f"contributes_to_shortfall: {context.contributes_to_shortfall}\n"
            + (
                "findings: "
                + json.dumps(
                    context.findings.model_dump(mode="json"),
                    default=str,
                )
                if context.findings
                else "findings: none on file"
            )
        )

    def _parse_recommendation(self, content: str) -> StrategyRecommendation:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise TypeError("recommendation is not a JSON object")
        return StrategyRecommendation.model_validate(payload)

    def _facts_missing(self, recommendation: StrategyRecommendation, tools: ToolBox) -> str:
        """Rule 1: the chosen track must be grounded in gathered facts."""
        if not tools.called("check_msmed_threshold"):
            return "no check_msmed_threshold call — statutory position unknown"
        if recommendation.action == "FINANCE" and not tools.called("check_treds_eligibility"):
            return "FINANCE recommended without a TReDS eligibility check"
        if recommendation.action == "ESCALATE" and not tools.called("calculate_interest"):
            return "ESCALATE recommended without the statutory interest figure"
        return ""


def _tool_flag(tools: ToolBox, tool: str, key: str, default: bool) -> bool:
    for call in tools.calls:
        if call.tool == tool and key in call.result:
            return bool(call.result[key])
    return default


def _tool_interest(tools: ToolBox) -> Decimal | None:
    for call in tools.calls:
        if call.tool == "calculate_interest":
            # The record is float-flattened for serialization; str() round-trips
            # exactly rather than introducing float→Decimal drift.
            return Decimal(str(call.result["interest"]))
    return None


def _tool_reason(tools: ToolBox, tool: str) -> str:
    for call in tools.calls:
        if call.tool == tool:
            return str(call.result.get("reason", ""))
    return ""


def get_strategist() -> Strategist:
    """The strategist the application should use.

    Returns `LLMStrategist` once a gateway is configured (OQ-02), otherwise the
    deterministic implementation — which is also the LLM path's fallback, so
    nothing here ever fails because the gateway is absent.
    """
    from app.config import settings

    if settings.llm_enabled:
        return LLMStrategist()
    return RuleBasedStrategist()


def _gateway_client() -> LLMClient:
    from app.config import settings

    return LiteLLMClient(
        gateway_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        timeout_s=settings.llm_request_timeout_s,
    )
