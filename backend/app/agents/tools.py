"""The agent tool boundary (ADR-002, CON-05, NFR-003).

This module is the *only* sanctioned way an agent obtains a statutory,
financial, or eligibility value. Agents select strategy; they never compute.

Every call through here is recorded — which function ran, with what arguments,
and what it returned. That record is what turns "the LLM didn't make the number
up" from a claim into something a user can inspect on screen, and what NFR-003
means when it asks that every statutory value trace to a named function.

The tools are deliberately thin wrappers. The arithmetic stays in
`rules_engine/`, so there is exactly one implementation of each rule and the
tool layer cannot quietly diverge from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.rules_engine.msmed import (
    calculate_appointed_day,
    calculate_interest,
    check_msmed_threshold,
)
from app.rules_engine.treds import check_treds_eligibility, simulate_financing


@dataclass
class ToolCall:
    """One invocation, kept for the audit trail."""

    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]

    def describe(self) -> str:
        """One line naming the function and what it produced."""
        summary = ", ".join(f"{k}={v}" for k, v in list(self.result.items())[:3])
        return f"{self.tool}() → {summary}"


@dataclass
class ToolBox:
    """Tools bound to one invoice, recording every call.

    An agent is handed a ToolBox rather than the rules functions directly, so
    there is no path to a statutory value that escapes the record.
    """

    as_of: date
    calls: list[ToolCall] = field(default_factory=list)

    def _record(self, tool: str, arguments: dict, result: dict) -> dict:
        self.calls.append(
            ToolCall(tool=tool, arguments=_jsonable(arguments), result=_jsonable(result))
        )
        return result

    # ------------------------------------------------------------- statutory

    def msmed_threshold(
        self,
        *,
        acceptance_date: date,
        agreed_credit_days: int,
        buyer_is_registered_enterprise: bool = True,
        supplier_is_msme: bool = True,
    ) -> dict:
        """Has this invoice crossed the MSMED statutory threshold? (FR-005)"""
        result = check_msmed_threshold(
            acceptance_date=acceptance_date,
            as_of=self.as_of,
            buyer_is_registered_enterprise=buyer_is_registered_enterprise,
            supplier_is_msme=supplier_is_msme,
            agreed_credit_days=agreed_credit_days,
        )
        return self._record(
            "check_msmed_threshold",
            {
                "acceptance_date": acceptance_date,
                "as_of": self.as_of,
                "agreed_credit_days": agreed_credit_days,
            },
            result,
        )

    def statutory_interest(
        self,
        *,
        principal: Decimal,
        acceptance_date: date,
        agreed_credit_days: int,
        rbi_bank_rate: Decimal,
    ) -> Decimal:
        """Statutory interest owed under MSMED §16.

        The one value an LLM must never produce. It goes in the legal dossier.
        """
        appointed_day = calculate_appointed_day(acceptance_date, agreed_credit_days)
        interest = calculate_interest(
            principal=principal,
            appointed_day=appointed_day,
            as_of=self.as_of,
            rbi_bank_rate=rbi_bank_rate,
        )
        self._record(
            "calculate_interest",
            {
                "principal": principal,
                "appointed_day": appointed_day,
                "as_of": self.as_of,
                "rbi_bank_rate": rbi_bank_rate,
            },
            {"interest": interest},
        )
        return interest

    # ------------------------------------------------------------- financing

    def treds_eligibility(
        self,
        *,
        invoice_amount: Decimal,
        due_date: date,
        invoice_is_buyer_approved: bool,
        buyer_participates_in_treds: bool,
        supplier_is_msme: bool = True,
    ) -> dict:
        """Can this invoice be discounted on TReDS? (FR-006)"""
        result = check_treds_eligibility(
            invoice_amount=invoice_amount,
            due_date=due_date,
            as_of=self.as_of,
            invoice_is_buyer_approved=invoice_is_buyer_approved,
            buyer_participates_in_treds=buyer_participates_in_treds,
            supplier_is_msme=supplier_is_msme,
        )
        return self._record(
            "check_treds_eligibility",
            {
                "invoice_amount": invoice_amount,
                "due_date": due_date,
                "buyer_participates_in_treds": buyer_participates_in_treds,
            },
            result,
        )

    def financing_terms(
        self,
        *,
        invoice_amount: Decimal,
        due_date: date,
        annual_discount_rate: Decimal,
    ) -> dict:
        """Simulated discounting terms (FR-012). Mock only — CON-07."""
        result = simulate_financing(
            invoice_amount=invoice_amount,
            due_date=due_date,
            as_of=self.as_of,
            annual_discount_rate=annual_discount_rate,
        )
        return self._record(
            "simulate_financing",
            {
                "invoice_amount": invoice_amount,
                "due_date": due_date,
                "annual_discount_rate": annual_discount_rate,
            },
            result,
        )

    # ---------------------------------------------------------------- record

    @property
    def trace(self) -> list[str]:
        """Human-readable call log, newest last."""
        return [call.describe() for call in self.calls]

    def called(self, tool: str) -> bool:
        return any(c.tool == tool for c in self.calls)


def _jsonable(payload: dict) -> dict:
    """Flatten Decimals and dates so the record survives serialization."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Decimal):
            out[key] = float(value)
        elif isinstance(value, date):
            out[key] = value.isoformat()
        elif isinstance(value, dict):
            out[key] = _jsonable(value)
        elif isinstance(value, list):
            out[key] = [str(v) for v in value]
        else:
            out[key] = value
    return out


# ---- LangChain tool wrappers -----------------------------------------------
# The same ToolBox methods, wrapped as langchain `StructuredTool`s so the
# framework's ToolNode can execute them in a graph. The ToolBox stays the
# recording seam: every call still lands in `calls`/`trace`, so the LLM path's
# audit trail is byte-identical to the rule-based path — a fallback is a
# genuine substitute, not a different code path.


class _MsmedArgs(BaseModel):
    acceptance_date: date = Field(description="Invoice acceptance date (ISO)")
    agreed_credit_days: int = Field(description="Agreed credit period in days")


class _InterestArgs(BaseModel):
    principal: Decimal = Field(description="Outstanding invoice amount")
    acceptance_date: date = Field(description="Invoice acceptance date (ISO)")
    agreed_credit_days: int = Field(description="Agreed credit period in days")
    rbi_bank_rate: Decimal = Field(description="RBI bank rate, e.g. 0.065")


class _TredsArgs(BaseModel):
    invoice_amount: Decimal = Field(description="Outstanding invoice amount")
    due_date: date = Field(description="Invoice due date (ISO)")
    invoice_is_buyer_approved: bool = Field(description="Buyer approved the invoice")
    buyer_participates_in_treds: bool = Field(
        description="Buyer is a registered TReDS participant"
    )


class _FinancingArgs(BaseModel):
    invoice_amount: Decimal = Field(description="Outstanding invoice amount")
    due_date: date = Field(description="Invoice due date (ISO)")
    annual_discount_rate: Decimal = Field(
        description="Annual discounting rate, e.g. 0.12"
    )


def build_toolbox_tools(box: ToolBox) -> list[StructuredTool]:
    """Wrap one ToolBox instance's methods as langchain tools.

    Args arrive JSON-typed (dates as ISO strings, money as numbers); pydantic
    coerces them to `date`/`Decimal` before the ToolBox method runs.
    """

    def _wrap(name: str, method_name: str, args: type[BaseModel]) -> StructuredTool:
        method = getattr(box, method_name)

        def _run(**kwargs: Any) -> dict[str, Any]:
            result = method(**kwargs)
            if isinstance(result, Decimal):
                result = {"interest": result}
            return _jsonable(result)

        return StructuredTool.from_function(
            func=_run,
            name=name,
            description=_description(name),
            args_schema=args,
        )

    return [
        _wrap("check_msmed_threshold", "msmed_threshold", _MsmedArgs),
        _wrap("calculate_interest", "statutory_interest", _InterestArgs),
        _wrap("check_treds_eligibility", "treds_eligibility", _TredsArgs),
        _wrap("simulate_financing", "financing_terms", _FinancingArgs),
    ]


def _description(name: str) -> str:
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema["description"]
    return name


# Schemas describing each tool to a language model. Kept beside the
# implementations so the two can't drift, and shaped for structured tool-calling
# APIs (OpenAI-style function schemas, which LangGraph consumes directly).
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "check_msmed_threshold",
        "description": (
            "Determine whether an invoice has crossed the MSMED Act statutory "
            "payment threshold. Returns statutory_flag, appointed_day, days_overdue "
            "and a reason. You MUST call this rather than reasoning about the "
            "45-day rule yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "acceptance_date": {"type": "string", "format": "date"},
                "agreed_credit_days": {"type": "integer"},
            },
            "required": ["acceptance_date", "agreed_credit_days"],
        },
    },
    {
        "name": "calculate_interest",
        "description": (
            "Compute statutory interest owed under MSMED §16 (compound, monthly "
            "rests, three times the RBI bank rate). Never compute this yourself — "
            "the figure goes into a legal dossier."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "principal": {"type": "number"},
                "acceptance_date": {"type": "string", "format": "date"},
                "agreed_credit_days": {"type": "integer"},
                "rbi_bank_rate": {"type": "number"},
            },
            "required": ["principal", "acceptance_date", "agreed_credit_days", "rbi_bank_rate"],
        },
    },
    {
        "name": "check_treds_eligibility",
        "description": (
            "Determine whether an invoice qualifies for TReDS discounting. Returns "
            "eligible plus every failing condition by name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_amount": {"type": "number"},
                "due_date": {"type": "string", "format": "date"},
                "invoice_is_buyer_approved": {"type": "boolean"},
                "buyer_participates_in_treds": {"type": "boolean"},
            },
            "required": [
                "invoice_amount",
                "due_date",
                "invoice_is_buyer_approved",
                "buyer_participates_in_treds",
            ],
        },
    },
    {
        "name": "simulate_financing",
        "description": (
            "Simulate TReDS discounting terms for an eligible invoice. Mock only — "
            "no live financial transaction ever occurs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_amount": {"type": "number"},
                "due_date": {"type": "string", "format": "date"},
                "annual_discount_rate": {"type": "number"},
            },
            "required": ["invoice_amount", "due_date", "annual_discount_rate"],
        },
    },
]
