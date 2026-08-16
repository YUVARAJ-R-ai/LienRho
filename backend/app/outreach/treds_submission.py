"""Mock TReDS financing submission (FR-012, CON-07, issue #15).

Assembles the payload an MSME would put in front of a financier, and simulates
what would come back. **No live transaction ever occurs** — CON-07 makes this a
hard boundary, not a phase-one limitation, and the generated artifact says so on
its face so nobody downstream can mistake it for a real submission.

Every figure here comes through `ToolBox`, not from arithmetic written in this
module. That is not ceremony: it means the financing cost quoted in the
submission is the same number, from the same function, that the Recovery
Strategy agent saw when it chose to finance — and the recorded trace proves it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.agents.tools import ToolBox
from app.canonical.models import CanonicalCustomer, CanonicalInvoice
from app.decision_engine.engine import ActionRecommendation, assert_executable
from app.outreach.formatting import format_date, format_inr

# Indicative discounting rate for the simulation. A real submission carries no
# rate at all — the financier bids one. This stands in so the user can see the
# shape of the economics before deciding.
DEMO_ANNUAL_DISCOUNT_RATE = Decimal("0.12")


class TredsIneligible(Exception):
    """Raised when an invoice that cannot be discounted is submitted anyway.

    Better to refuse than to generate a submission that would be rejected: an
    artifact that looks legitimate but cannot succeed is worse than no artifact.
    """

    def __init__(self, invoice_id: str, failing_conditions: list[str]):
        self.invoice_id = invoice_id
        self.failing_conditions = failing_conditions
        super().__init__(f"{invoice_id} is not TReDS-eligible: {'; '.join(failing_conditions)}")


class TredsPayload(BaseModel):
    """Exactly the five fields prd.md §719–725 specifies. Do not widen casually.

    A financing platform's intake schema is not ours to extend — extra fields
    are what a real integration rejects the whole submission over.
    """

    invoice_id: str
    amount: Decimal
    buyer: str
    due_date: date
    financing_required: bool


class TredsSimulation(BaseModel):
    """Simulated response: eligibility, rate, proceeds, cost (FR-012)."""

    eligible: bool
    failing_conditions: list[str] = Field(default_factory=list)
    annual_discount_rate: Decimal
    days_to_due: int
    financing_cost: Decimal
    estimated_proceeds: Decimal


class TredsSubmission(BaseModel):
    """The complete mock submission artifact."""

    payload: TredsPayload
    simulation: TredsSimulation
    # Not configurable. CON-07 is a constraint, not a default.
    mock: bool = Field(
        default=True,
        description="Always true — LIENRHO never performs a live TReDS transaction.",
    )
    notice: str = (
        "SIMULATION ONLY — this submission is not transmitted to any TReDS "
        "platform and no financing has been arranged (CON-07)."
    )
    tool_trace: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _proceeds_reconcile(self) -> TredsSubmission:
        """FR-012 AC: `estimated_proceeds = amount − simulated_financing_cost`.

        Enforced on the model rather than in a test, so it holds for every
        submission ever constructed — including one a future caller assembles by
        hand from figures that came from somewhere else. The amount lives on the
        payload and the cost on the simulation, so this is the only place both
        are in scope and the identity can actually be checked.

        An MSME deciding whether to discount is deciding on this number.
        """
        expected = self.payload.amount - self.simulation.financing_cost
        if self.simulation.estimated_proceeds != expected:
            raise ValueError(
                f"estimated_proceeds ({self.simulation.estimated_proceeds}) must equal "
                f"amount ({self.payload.amount}) minus financing_cost "
                f"({self.simulation.financing_cost}) = {expected}"
            )
        return self

    def to_markdown(self) -> str:
        """Render for the UI. Markdown, not PDF — see the plan for #15."""
        p, s = self.payload, self.simulation
        lines = [
            f"# Mock TReDS submission — {p.invoice_id}",
            "",
            f"> **{self.notice}**",
            "",
            "## Submission payload",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| `invoice_id` | {p.invoice_id} |",
            f"| `amount` | {format_inr(p.amount, paise=True)} |",
            f"| `buyer` | {p.buyer} |",
            f"| `due_date` | {p.due_date.isoformat()} |",
            f"| `financing_required` | {str(p.financing_required).lower()} |",
            "",
            "## Simulated terms",
            "",
            "| | |",
            "|---|---|",
            f"| Eligibility | {'Eligible' if s.eligible else 'Not eligible'} |",
            f"| Days to due date | {s.days_to_due} |",
            f"| Indicative discount rate | {s.annual_discount_rate:.2%} per annum |",
            f"| Financing cost | {format_inr(s.financing_cost, paise=True)} |",
            f"| **Estimated proceeds** | **{format_inr(s.estimated_proceeds, paise=True)}** |",
            "",
            (
                f"Discounting {format_inr(p.amount)} due {format_date(p.due_date)} "
                f"releases {format_inr(s.estimated_proceeds)} now, at a cost of "
                f"{format_inr(s.financing_cost, paise=True)}."
            ),
        ]

        if self.tool_trace:
            lines += [
                "",
                "## How these figures were produced",
                "",
                (
                    "Every value above came from a deterministic function, not from a "
                    "language model (CON-05, NFR-003):"
                ),
                "",
                *(f"- `{call}`" for call in self.tool_trace),
            ]

        return "\n".join(lines)


def build_treds_submission(
    *,
    recommendation: ActionRecommendation,
    invoice: CanonicalInvoice,
    customer: CanonicalCustomer | None,
    as_of: date,
    annual_discount_rate: Decimal = DEMO_ANNUAL_DISCOUNT_RATE,
) -> TredsSubmission:
    """Generate the mock submission for an approved FINANCE action.

    Raises `ApprovalRequired` if the action has not been approved (FR-010) and
    `TredsIneligible` if the invoice would not qualify.
    """
    # The gate first, before anything is assembled. An artifact that exists is
    # an artifact someone can act on.
    assert_executable(recommendation)

    tools = ToolBox(as_of=as_of)
    eligibility = tools.treds_eligibility(
        invoice_amount=invoice.invoice_amount,
        due_date=invoice.due_date,
        invoice_is_buyer_approved=invoice.acceptance_date is not None,
        buyer_participates_in_treds=(customer.treds_status == "PARTICIPANT" if customer else False),
    )

    if not eligibility["eligible"]:
        raise TredsIneligible(invoice.invoice_id, eligibility["failing_conditions"])

    terms = tools.financing_terms(
        invoice_amount=invoice.invoice_amount,
        due_date=invoice.due_date,
        annual_discount_rate=annual_discount_rate,
    )

    return TredsSubmission(
        payload=TredsPayload(
            invoice_id=invoice.invoice_id,
            amount=invoice.invoice_amount,
            buyer=customer.customer_name if customer else invoice.customer_id,
            due_date=invoice.due_date,
            financing_required=True,
        ),
        simulation=TredsSimulation(
            eligible=True,
            failing_conditions=[],
            annual_discount_rate=annual_discount_rate,
            days_to_due=terms["days_to_due"],
            financing_cost=terms["financing_cost"],
            estimated_proceeds=terms["estimated_proceeds"],
        ),
        tool_trace=tools.trace,
    )
