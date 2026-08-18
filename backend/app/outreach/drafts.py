"""Draft outreach messages (FR-011, issue #15).

Generates a reminder a human then edits and sends. Nothing here sends anything:
`OQ-01` defaults to drafted-in-UI for this build, so the draft is the artifact
and the send is the user's own action in their own client.

**Why this one is allowed to be model-written later.** A reminder is prose, not
a statutory or financial computation, so `CON-05` does not forbid an LLM from
writing it — the amount and dates are interpolated from the invoice rather than
generated, which is what keeps the numbers safe regardless of who writes the
sentences around them. That makes this the one artifact where the LLM has real
work to do, so it follows the same two-implementations pattern as the
Investigator and the Strategist: `TemplateReminderDrafter` runs today,
`LLMReminderDrafter` is unblocked by `OQ-02`, and both return the same validated
`ReminderDraft`.

The dossier and the TReDS submission deliberately do *not* work this way. Those
carry figures that go to a financier or a tribunal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.agents.schemas import InvestigatorFindings
from app.outreach.formatting import format_date, format_inr


class DraftChannel(StrEnum):
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"


class ReminderDraft(BaseModel):
    """A reminder awaiting a human's edit and send (FR-011)."""

    invoice_id: str
    channel: DraftChannel
    # WhatsApp has no subject line; email does. Modelled as optional rather than
    # empty-string so a renderer can tell "no subject" from "blank subject".
    subject: str | None = None
    body: str
    # FR-011 AC: the draft must remain editable before it goes out. Nothing in
    # this system sends a message the user has not had the chance to change.
    editable: bool = Field(
        default=True,
        description="Always true — a draft is never final until a human edits and sends it.",
    )

    def to_markdown(self) -> str:
        """Render for display, alongside the other two artifacts.

        The body is left exactly as written — this is text the user will copy
        into their own mail or WhatsApp client, and reflowing it would mean
        what they send is not what they reviewed.
        """
        if self.subject:
            return f"**Subject:** {self.subject}\n\n{self.body}"
        return self.body


@dataclass
class DraftContext:
    """Everything a drafter may reference for one invoice."""

    invoice_id: str
    customer_name: str
    invoice_amount: Decimal
    due_date: date
    days_overdue: int
    supplier_name: str
    findings: InvestigatorFindings | None = None


class ReminderDrafter(ABC):
    """One implementation per generation strategy (template, LLM, ...)."""

    @abstractmethod
    def draft(self, context: DraftContext, *, channel: DraftChannel) -> ReminderDraft: ...


class TemplateReminderDrafter(ReminderDrafter):
    """Deterministic templates. Runs with no external dependency.

    Tone is the point of having two channels. An email to a corporate accounts
    department and a WhatsApp message to an owner who reads it on a phone are
    not the same document, and sending the formal version over WhatsApp reads as
    a threat rather than a nudge.
    """

    def draft(self, context: DraftContext, *, channel: DraftChannel) -> ReminderDraft:
        if channel is DraftChannel.EMAIL:
            return self._email(context)
        return self._whatsapp(context)

    # ----------------------------------------------------------------- email

    def _email(self, ctx: DraftContext) -> ReminderDraft:
        amount = format_inr(ctx.invoice_amount)
        due = format_date(ctx.due_date)

        lines = [
            f"Dear {ctx.customer_name} team,",
            "",
            (
                f"This is a reminder regarding invoice {ctx.invoice_id} for {amount}, "
                f"which was due on {due}{self._overdue_clause(ctx)}."
            ),
        ]

        evidence = self._evidence_sentence(ctx)
        if evidence:
            lines += ["", evidence]

        lines += [
            "",
            self._ask(ctx),
            "",
            (
                "If the payment has already been released, please share the UTR or "
                "payment reference and we will reconcile it at our end."
            ),
            "",
            "Thank you,",
            ctx.supplier_name,
        ]

        return ReminderDraft(
            invoice_id=ctx.invoice_id,
            channel=DraftChannel.EMAIL,
            subject=f"Payment reminder — invoice {ctx.invoice_id} ({amount}, due {due})",
            body="\n".join(lines),
        )

    # -------------------------------------------------------------- whatsapp

    def _whatsapp(self, ctx: DraftContext) -> ReminderDraft:
        amount = format_inr(ctx.invoice_amount)
        due = format_date(ctx.due_date)

        lines = [
            (
                f"Hello {ctx.customer_name} — a quick follow-up on invoice "
                f"{ctx.invoice_id} ({amount}), which was due on {due}"
                f"{self._overdue_clause(ctx)}."
            )
        ]

        evidence = self._evidence_sentence(ctx, conversational=True)
        if evidence:
            lines.append(evidence)

        lines.append(self._ask(ctx, conversational=True))
        lines.append(f"— {ctx.supplier_name}")

        return ReminderDraft(
            invoice_id=ctx.invoice_id,
            channel=DraftChannel.WHATSAPP,
            subject=None,
            body="\n\n".join(lines),
        )

    # ----------------------------------------------------------------- parts

    @staticmethod
    def _overdue_clause(ctx: DraftContext) -> str:
        if ctx.days_overdue <= 0:
            return ""
        return f" and is now {ctx.days_overdue} days overdue"

    @staticmethod
    def _evidence_sentence(ctx: DraftContext, *, conversational: bool = False) -> str | None:
        """Reference what FR-007 actually found in the correspondence.

        This is the whole reason the draft is worth generating rather than
        typing: it cites the customer's own words back to them. A reminder that
        ignores the commitment they made last week reads as a system that hasn't
        been paying attention — and it wastes the strongest thing we have.

        A promise the Investigator judged *not* credible is still quoted, but
        without softening language. The prior broken promises are our internal
        assessment and stay internal; putting them in a message to the customer
        would be an accusation, and it isn't the drafter's place to make one.
        """
        findings = ctx.findings
        if findings is None:
            return None

        if findings.dispute_detected:
            return (
                "We understand there is an open concern on this invoice. "
                "Could you confirm the specifics so we can resolve it and close this out?"
            )

        if findings.payment_promise and findings.promised_date:
            when = format_date(findings.promised_date)
            if conversational:
                return f"You had mentioned payment would be released by {when} — has that gone through?"
            return (
                f"Our records show a commitment to release this payment by {when}. "
                "We have not seen it credited yet."
            )

        if findings.payment_promise:
            return (
                "You had indicated this would be settled shortly — could you confirm "
                "the expected date?"
            )

        return None

    @staticmethod
    def _ask(ctx: DraftContext, *, conversational: bool = False) -> str:
        """Close with one specific request. A reminder without an ask is a notice."""
        if ctx.findings is not None and ctx.findings.dispute_detected:
            return (
                "Happy to get on a call this week if that's easier."
                if conversational
                else "We are happy to schedule a call this week to work through it."
            )
        if conversational:
            return "Could you share the expected payment date so we can plan our end?"
        return (
            "Could you confirm the expected payment date so we can plan our "
            "working-capital position accordingly?"
        )


class LLMReminderDrafter(ReminderDrafter):
    """LLM implementation — blocked on OQ-02.

    Intended shape: a structured-output call returning `ReminderDraft` directly,
    given the invoice facts, the Investigator's findings, and the relationship
    context (how long, how large, how reliably they have paid before).

    Two rules the implementation must hold to:

    1. **Interpolate the numbers, never generate them.** The amount, the due
       date, and the overdue count are passed in and substituted. A model that
       writes "₹4.2 lakh" from memory has invented a figure, and the customer
       will notice before we do.
    2. **Fall through to `TemplateReminderDrafter` on any failure.** A
       template-shaped reminder is perfectly usable; a failed request means the
       user is staring at an empty compose box.
    """

    def __init__(self, fallback: ReminderDrafter | None = None):
        self._fallback = fallback or TemplateReminderDrafter()

    def draft(self, context: DraftContext, *, channel: DraftChannel) -> ReminderDraft:
        raise NotImplementedError(
            "LLM provider not selected — see OQ-02. Use TemplateReminderDrafter."
        )


def get_drafter() -> ReminderDrafter:
    """The drafter the application should use.

    Returns the template implementation while OQ-02 is open. Switching is a
    one-line change here once a provider and key exist.
    """
    return TemplateReminderDrafter()
