"""Receivables Investigator (FR-007, issue #12).

Reads a customer's correspondence for one invoice and returns structured
findings: is there a payment promise, for when, is there a dispute, and how much
should we believe it.

**Two implementations behind one interface.**

`RuleBasedInvestigator` runs today with no external dependency. `LLMInvestigator`
is the intended production path and is unblocked the moment `OQ-02` resolves.
Both return the same Pydantic-validated `InvestigatorFindings`, so the Decision
Engine cannot tell them apart — which is the point of ADR-002's structured-I/O
rule, and also what stops the agent layer from blocking everyone else.

The rule-based version is not a placeholder to be deleted. It stays as the
fallback path so a missing key, a rate limit, or a malformed model response
degrades the recommendation rather than failing the request — and it gives the
LLM implementation something to be measured against.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm_client import (
    CHEAP_TIER,
    LiteLLMChatModel,
    LiteLLMClient,
    LLMClient,
)
from app.agents.schemas import InvestigatorFindings
from app.data.communications import (
    PROMISE_HISTORY,
    CommunicationThread,
    Direction,
    promise_reliability,
)

# Phrases that commit to paying. Ordered strongest first — a firm commitment
# should outweigh a hedge appearing later in the same message.
_PROMISE_PATTERNS: list[tuple[str, float]] = [
    (r"\bwill clear\b", 0.9),
    (r"\bwill settle\b", 0.9),
    (r"\byou have my word\b", 0.9),
    (r"\bpayment is in process\b", 0.85),
    (r"\bwill be (?:paid|released|processed)\b", 0.8),
    (r"\bwill share (?:utr|proof)\b", 0.8),
    (r"\bwill process\b", 0.7),
    (r"\bwill pay\b", 0.85),
    (r"\bwe are arranging\b", 0.55),
    (r"\bgive us \d+ days\b", 0.5),
    (r"\bnext payment run\b", 0.6),
    (r"\bin this week'?s run\b", 0.6),
]

# A dispute blocks escalation and financing, so these are matched conservatively
# — a vague complaint is not a dispute.
_DISPUTE_PATTERNS: list[tuple[str, str]] = [
    (r"\bdid not match\b", "Goods did not match the approved sample"),
    (r"\bshade variation\b", "Quality dispute: shade variation"),
    (r"\bquality (?:issue|problem|dispute)\b", "Quality dispute raised"),
    (r"\bshort (?:supply|shipment)\b", "Short supply claimed"),
    (r"\bdamaged\b", "Goods reported damaged"),
    (r"\bwrong (?:item|quantity|rate)\b", "Billing or fulfilment discrepancy"),
    (r"\bcannot process the full invoice\b", "Customer withholding full payment"),
    (r"\bfull payment is not possible\b", "Customer withholding full payment"),
    (r"\bpartial settlement\b", "Customer proposing partial settlement"),
    (r"\bqc\b", "QC objection raised"),
]

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


class Investigator(ABC):
    """Interface both implementations honour."""

    @abstractmethod
    def investigate(
        self, thread: CommunicationThread, *, as_of: date
    ) -> InvestigatorFindings: ...


class RuleBasedInvestigator(Investigator):
    """Deterministic extraction. No network, no key, no variance.

    Reads only inbound messages — what we said to the customer is not evidence
    of their intent.
    """

    def investigate(
        self, thread: CommunicationThread, *, as_of: date
    ) -> InvestigatorFindings:
        inbound = thread.inbound
        if not inbound:
            return InvestigatorFindings(
                payment_promise=False,
                dispute_detected=False,
                confidence=0.9,  # Silence is unambiguous, if unhelpful.
                evidence=[
                    f"No response across {thread.outbound_count} outbound messages"
                ],
            )

        dispute, dispute_summary, dispute_evidence = self._detect_dispute(inbound)
        promise, promise_strength, promise_evidence = self._detect_promise(inbound)
        promised_date = (
            self._extract_date(inbound, as_of=as_of) if promise else None
        )

        reliability = promise_reliability(thread.customer_id)
        broken = self._broken_promise_count(thread.customer_id)

        evidence = dispute_evidence + promise_evidence
        if promise and broken:
            evidence.append(
                f"Customer has made {broken} prior promise(s) and kept none of them"
            )

        return InvestigatorFindings(
            payment_promise=promise,
            promised_date=promised_date,
            dispute_detected=dispute,
            dispute_summary=dispute_summary,
            confidence=self._confidence(promise, promise_strength, dispute),
            prior_broken_promises=broken,
            promise_reliability=reliability,
            evidence=evidence or ["Correspondence contains no actionable signal"],
        )

    # ---------------------------------------------------------------- helpers

    def _detect_dispute(self, inbound) -> tuple[bool, str | None, list[str]]:
        for message in inbound:
            body = message.body.lower()
            for pattern, summary in _DISPUTE_PATTERNS:
                if re.search(pattern, body):
                    return True, summary, [f'{message.sent_on}: "{message.body[:140]}"']
        return False, None, []

    def _detect_promise(self, inbound) -> tuple[bool, float, list[str]]:
        best_strength = 0.0
        evidence: list[str] = []

        # Later messages supersede earlier ones — a customer's most recent
        # position is the one that counts.
        for message in sorted(inbound, key=lambda m: m.sent_on, reverse=True):
            body = message.body.lower()
            for pattern, strength in _PROMISE_PATTERNS:
                if re.search(pattern, body) and strength > best_strength:
                    best_strength = strength
                    evidence = [f'{message.sent_on}: "{message.body[:140]}"']
            if best_strength >= 0.85:
                break

        return best_strength > 0.0, best_strength, evidence

    def _extract_date(self, inbound, *, as_of: date) -> date | None:
        """Resolve a stated payment date. Returns None when the customer hedged.

        Deliberately conservative: "by month end" and "in 10 days" are not
        commitments to a date, and inventing one would put a fabricated
        `promised_date` in front of the user.
        """
        for message in sorted(inbound, key=lambda m: m.sent_on, reverse=True):
            body = message.body.lower()

            # Explicit day-of-month: "21st", "on 25/06".
            day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", body)
            if day_match:
                day = int(day_match.group(1))
                if 1 <= day <= 31:
                    resolved = self._next_occurrence_of_day(day, message.sent_on)
                    if resolved:
                        return resolved

            # Named weekday: "by Friday".
            for name, index in _WEEKDAYS.items():
                if re.search(rf"\b{name}\b", body):
                    return self._next_weekday(message.sent_on, index)

        return None

    @staticmethod
    def _next_occurrence_of_day(day: int, after: date) -> date | None:
        for month_offset in (0, 1):
            month = after.month + month_offset
            year = after.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if candidate >= after:
                return candidate
        return None

    @staticmethod
    def _next_weekday(after: date, weekday: int) -> date:
        delta = (weekday - after.weekday()) % 7 or 7
        return after + timedelta(days=delta)

    @staticmethod
    def _broken_promise_count(customer_id: str) -> int:
        from app.data.communications import PROMISE_HISTORY

        history = PROMISE_HISTORY.get(customer_id)
        if not history:
            return 0
        return history["promises_made"] - history["promises_kept"]

    @staticmethod
    def _confidence(promise: bool, strength: float, dispute: bool) -> float:
        # An explicit dispute is about as unambiguous as this correspondence gets.
        if dispute:
            return 0.9
        if promise:
            # Track the strength of the phrase actually matched.
            return round(min(0.5 + strength * 0.45, 0.95), 2)
        return 0.6


def render_thread(thread: CommunicationThread) -> str:
    """Render a communication thread into prompt text (FR-007).

    Only inbound messages are evidence of the customer's intent, but outbound
    messages provide the context (what was chased, how often) that lets the
    model weigh a reply. So the full thread is shown, dated oldest-first.
    """
    if not thread.messages:
        return "No correspondence on file for this invoice."

    lines = []
    for message in sorted(thread.messages, key=lambda m: m.sent_on):
        speaker = "customer" if message.direction is Direction.INBOUND else "us"
        lines.append(f"{message.sent_on.isoformat()} [{message.channel.value}] {speaker}: {message.body}")
    return "\n".join(lines)


class LLMInvestigator(Investigator):
    """LLM implementation (OQ-02, issue #12) — a single structured-output call.

    The thread is rendered into the prompt and `promise_reliability` is supplied
    as *context*, not asked for — it is derived from history, and asking the
    model to read it off the text would be both slower and wrong.

    Whatever comes back is validated against `InvestigatorFindings`. On any
    failure — refusal, malformed output, timeout, rate limit — it falls through
    to `RuleBasedInvestigator` rather than raising. A missing finding degrades a
    recommendation; an exception loses the whole action queue.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        fallback: Investigator | None = None,
    ):

        self._client = client or _gateway_client()
        self._fallback = fallback or RuleBasedInvestigator()

    def investigate(
        self, thread: CommunicationThread, *, as_of: date
    ) -> InvestigatorFindings:
        model = LiteLLMChatModel(client=self._client, model_tier=CHEAP_TIER)
        chain = model.with_structured_output(InvestigatorFindings)
        try:
            findings = chain.invoke(self._build_messages(thread, as_of=as_of))
            return self._fill_history(findings, thread)
        except Exception:  # noqa: BLE001 - every failure path degrades to the fallback
            return self._fallback.investigate(thread, as_of=as_of)

    def _build_messages(
        self, thread: CommunicationThread, *, as_of: date
    ) -> list[SystemMessage | HumanMessage]:
        reliability = promise_reliability(thread.customer_id)
        reliability_line = (
            f"This customer has kept {reliability:.0%} of their past payment promises."
            if reliability is not None
            else "This customer has never made a prior payment promise."
        )

        return [
            SystemMessage(
                content=(
                    "You read customer payment correspondence for receivables "
                    "collection. You return findings as JSON matching the schema "
                    "you are given. Rules:\n"
                    "- Only messages from the customer are evidence of their intent.\n"
                    "- A payment promise must be an explicit or clearly implied "
                    "commitment to pay. 'Checking with accounts', 'will revert', "
                    "acknowledgements, and hedged phrases are NOT promises.\n"
                    "- Set promised_date ONLY when a concrete date was stated "
                    "('Friday', 'the 21st', 'by month end' counts as vague — do not "
                    "invent one).\n"
                    "- A dispute requires a real quality/quantity/billing complaint, "
                    "not a delay excuse.\n"
                    "- Never invent evidence. Quote or closely paraphrase the "
                    "customer's own words.\n"
                    f"- {reliability_line}"
                ),
            ),
            HumanMessage(
                content=(
                    f"Invoice {thread.invoice_id} for customer {thread.customer_id} "
                    f"(as of {as_of.isoformat()}).\n\n"
                    f"Correspondence:\n{render_thread(thread)}"
                ),
            ),
        ]

    def _fill_history(
        self, findings: InvestigatorFindings, thread: CommunicationThread
    ) -> InvestigatorFindings:
        # The model must not invent history it was never given. Promise
        # reliability is derived from observed data (ADR-004 discipline), so any
        # value the model produced is discarded and the real one is filled in
        # from history — the same source the rule-based path uses.
        reliability = promise_reliability(thread.customer_id)
        history = PROMISE_HISTORY.get(thread.customer_id)
        return findings.model_copy(
            update={
                "promise_reliability": reliability,
                "prior_broken_promises": (
                    history["promises_made"] - history["promises_kept"]
                    if history
                    else 0
                ),
            }
        )


def get_investigator() -> Investigator:
    """The investigator the application should use.

    Returns `LLMInvestigator` once a gateway is configured (OQ-02), otherwise
    the rule-based implementation — which is also the LLM path's fallback, so
    nothing here ever fails because the gateway is absent.
    """
    from app.config import settings

    if settings.llm_enabled:
        return LLMInvestigator()
    return RuleBasedInvestigator()


def _gateway_client() -> LLMClient:
    from app.config import settings

    return LiteLLMClient(
        gateway_url=settings.llm_gateway_url,
        api_key=settings.llm_api_key,
        timeout_s=settings.llm_request_timeout_s,
    )
