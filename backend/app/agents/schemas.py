"""Structured I/O contracts for every agent (ADR-002, FR-007).

The rule this file exists to enforce: **no agent output reaches the Decision
Engine unless it validates against one of these models.** Free text from a
language model is never passed along as-is.

Constraining the shape here also means the LLM implementation and the
deterministic fallback are interchangeable — both must produce the same
validated object, so the Decision Engine cannot tell them apart and doesn't
need to.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class InvestigatorFindings(BaseModel):
    """Receivables Investigator output (FR-007).

    The four fields FR-007 names are required. `promise_reliability` and
    `prior_broken_promises` are extensions: a promise from a customer who has
    broken three is not the same signal as one from a customer who has kept six,
    and collapsing them loses the only thing that makes this layer worth having.
    """

    payment_promise: bool = Field(
        description="Did the customer commit to paying, explicitly or clearly by implication?"
    )
    promised_date: date | None = Field(
        default=None,
        description="The date committed to, if one was actually stated. Null if vague.",
    )
    dispute_detected: bool = Field(
        description="Has the customer raised a quality, quantity, or billing dispute?"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in this reading of the correspondence.",
    )

    dispute_summary: str | None = Field(
        default=None, description="One line on the nature of the dispute, if any."
    )
    prior_broken_promises: int = Field(
        default=0,
        ge=0,
        description="Promises this customer has made and not kept, from history.",
    )
    promise_reliability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Share of past promises kept. Null if they have never promised.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Quoted or paraphrased lines the findings rest on.",
    )

    @field_validator("promised_date")
    @classmethod
    def _date_requires_a_promise(cls, v: date | None, info) -> date | None:
        # A date with no promise is incoherent, and it would flow straight into
        # the recommendation. Reject it here rather than let it through.
        if v is not None and info.data.get("payment_promise") is False:
            raise ValueError("promised_date set without payment_promise")
        return v

    @property
    def promise_is_credible(self) -> bool:
        """Whether the promise should actually move the recommendation.

        A promise from a customer who has broken every previous one is evidence
        of a pattern, not of intent to pay.
        """
        if not self.payment_promise:
            return False
        if self.promise_reliability is None:
            # Never promised before — take it at face value but no more.
            return True
        return self.promise_reliability >= 0.5


class StrategyRecommendation(BaseModel):
    """Recovery Strategy agent output (FR-008).

    The agent selects a track and cites its reasons. It never produces a
    statutory or financial figure — those arrive via tool calls into
    `rules_engine` and are echoed here only as references (ADR-002).
    """

    action: str = Field(description="FOLLOW_UP, FINANCE, or ESCALATE")
    reason: str = Field(description="Why this track, in one sentence a user can read.")
    deciding_factors: list[str] = Field(
        default_factory=list,
        description="The specific inputs that drove the choice.",
    )
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("action")
    @classmethod
    def _known_action(cls, v: str) -> str:
        allowed = {"FOLLOW_UP", "FINANCE", "ESCALATE"}
        if v not in allowed:
            raise ValueError(f"action must be one of {sorted(allowed)}, got {v!r}")
        return v
