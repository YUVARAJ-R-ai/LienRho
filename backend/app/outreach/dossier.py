"""Statutory escalation dossier (FR-013, CON-08, issue #15).

Assembles the document an MSME would take to MSME Samadhaan ODR: who is owed,
by whom, since when, what was said, and what interest has accrued under MSMED
§16. **It is generated for manual filing and never submitted** — CON-08 is a
hard boundary. The document says so on its own first page, because the one
place that assurance matters is inside the artifact that leaves the system.

Two rules this module exists to hold:

1. **The interest figure comes from `calculate_interest()` via `ToolBox`**, so
   the dossier's most consequential number appears in the audit trail as a
   recorded call with its arguments. FR-013's acceptance criterion names this
   explicitly, and it is the difference between a document a tribunal can rely
   on and one it cannot.
2. **Missing evidence is stated as missing.** No section is quietly dropped and
   nothing is inferred to fill a gap. A dossier that silently omits proof of
   delivery invites the reader to assume it exists; one that says "not on file"
   tells the user what they still have to go and find. Fabricating a document
   reference in a legal filing would be the worst thing this system could do.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.agents.tools import ToolBox
from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    SupplierProfile,
)
from app.data.communications import CommunicationThread
from app.decision_engine.engine import ActionRecommendation, assert_executable
from app.outreach.formatting import format_date, format_inr
from app.rules_engine.msmed import MSMED_INTEREST_MULTIPLIER

# The RBI bank rate notified for the demo period. A real filing must use the
# rate notified for the period actually being claimed — this is a demo constant,
# not a default worth inheriting.
DEMO_RBI_BANK_RATE = Decimal("0.065")

# FR-013 names these seven. The order is the reading order of the filing:
# who is claiming, what for, the history behind it, the evidence, the money,
# and what still has to be attached.
SECTION_TITLES = (
    "Udyam information",
    "Invoice",
    "Payment history",
    "Proof of delivery",
    "Communication evidence",
    "Statutory interest calculation",
    "Required documentation",
)


class DossierSection(BaseModel):
    title: str
    body: str


class EscalationDossier(BaseModel):
    """The assembled filing packet (FR-013)."""

    invoice_id: str
    customer_name: str
    generated_on: date
    statutory_interest: Decimal
    total_claim: Decimal
    sections: list[DossierSection]
    # Not configurable. CON-08 is a constraint, not a default.
    filing_notice: str = (
        "PREPARED FOR MANUAL FILING — LIENRHO does not submit this document to "
        "MSME Samadhaan or any other authority. Review it with your legal "
        "advisor before filing (CON-08)."
    )
    tool_trace: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Statutory escalation dossier — {self.invoice_id}",
            "",
            f"**Respondent:** {self.customer_name}  ",
            f"**Prepared on:** {format_date(self.generated_on)}  ",
            (
                f"**Total claim:** {format_inr(self.total_claim, paise=True)} "
                f"(principal + statutory interest)"
            ),
            "",
            f"> **{self.filing_notice}**",
        ]
        for section in self.sections:
            lines += ["", f"## {section.title}", "", section.body]

        if self.tool_trace:
            lines += [
                "",
                "## Provenance of computed figures",
                "",
                (
                    "Every statutory figure in this dossier was produced by a named "
                    "deterministic function, not by a language model (CON-05, "
                    "NFR-003, ADR-002):"
                ),
                "",
                *(f"- `{call}`" for call in self.tool_trace),
            ]

        return "\n".join(lines)


def build_dossier(
    *,
    recommendation: ActionRecommendation,
    invoice: CanonicalInvoice,
    customer: CanonicalCustomer | None,
    supplier: SupplierProfile,
    payments: list[CanonicalPayment],
    thread: CommunicationThread | None,
    as_of: date,
    rbi_bank_rate: Decimal = DEMO_RBI_BANK_RATE,
) -> EscalationDossier:
    """Assemble the dossier for an approved ESCALATE action.

    Raises `ApprovalRequired` if the action has not been approved (FR-010).
    """
    # The gate first. A legal document that exists is a legal document someone
    # can file, approved or not.
    assert_executable(recommendation)

    acceptance = invoice.acceptance_date or invoice.invoice_date
    agreed_credit_days = (invoice.due_date - invoice.invoice_date).days
    customer_name = customer.customer_name if customer else invoice.customer_id

    tools = ToolBox(as_of=as_of)
    threshold = tools.msmed_threshold(
        acceptance_date=acceptance,
        agreed_credit_days=agreed_credit_days,
    )
    interest = tools.statutory_interest(
        principal=invoice.invoice_amount,
        acceptance_date=acceptance,
        agreed_credit_days=agreed_credit_days,
        rbi_bank_rate=rbi_bank_rate,
    )

    sections = [
        DossierSection(title=SECTION_TITLES[0], body=_udyam_section(supplier)),
        DossierSection(
            title=SECTION_TITLES[1],
            body=_invoice_section(invoice, customer_name, threshold),
        ),
        DossierSection(
            title=SECTION_TITLES[2],
            body=_payment_history_section(payments, invoice.customer_id),
        ),
        DossierSection(title=SECTION_TITLES[3], body=_proof_of_delivery_section(invoice)),
        DossierSection(title=SECTION_TITLES[4], body=_communication_section(thread)),
        DossierSection(
            title=SECTION_TITLES[5],
            body=_interest_section(invoice, threshold, interest, rbi_bank_rate),
        ),
        DossierSection(title=SECTION_TITLES[6], body=_required_documentation_section()),
    ]

    return EscalationDossier(
        invoice_id=invoice.invoice_id,
        customer_name=customer_name,
        generated_on=as_of,
        statutory_interest=interest,
        total_claim=invoice.invoice_amount + interest,
        sections=sections,
        tool_trace=tools.trace,
    )


# ------------------------------------------------------------------ sections


def _udyam_section(supplier: SupplierProfile) -> str:
    return "\n".join(
        [
            f"**Legal name:** {supplier.legal_name}  ",
            f"**Udyam registration:** {supplier.udyam_registration_number}  ",
            f"**Enterprise category:** {supplier.enterprise_category}  ",
            f"**Registered address:** {supplier.address}  ",
            f"**Contact:** {supplier.contact_email}",
            "",
            (
                "The supplier is a registered MSME and the claim is brought under the "
                "Micro, Small and Medium Enterprises Development Act, 2006."
            ),
        ]
    )


def _invoice_section(invoice: CanonicalInvoice, customer_name: str, threshold: dict) -> str:
    return "\n".join(
        [
            f"**Invoice number:** {invoice.invoice_id}  ",
            f"**Buyer:** {customer_name}  ",
            f"**Invoice amount:** {format_inr(invoice.invoice_amount, paise=True)}  ",
            f"**Invoice date:** {format_date(invoice.invoice_date)}  ",
            (
                f"**Date of acceptance:** "
                f"{format_date(invoice.acceptance_date or invoice.invoice_date)}"
                f"{'' if invoice.acceptance_date else ' *(acceptance not separately recorded; invoice date used)*'}  "
            ),
            f"**Agreed due date:** {format_date(invoice.due_date)}  ",
            f"**Appointed day (MSMED §15):** {format_date(threshold['appointed_day'])}  ",
            f"**Days overdue as of preparation:** {threshold['days_overdue']}  ",
            f"**Payment status:** {invoice.payment_status.value}",
            "",
            f"Statutory threshold assessment: {threshold['reason']}.",
        ]
    )


def _payment_history_section(payments: list[CanonicalPayment], customer_id: str) -> str:
    """Prior conduct. A single late invoice is an incident; a pattern is a case."""
    history = [p for p in payments if p.customer_id == customer_id]
    if not history:
        return (
            "No prior settled invoices are on record for this buyer. This claim "
            "cannot be supported by a history of delayed payment."
        )

    settled = [p for p in history if p.days_delayed is not None]
    late = [p for p in settled if (p.days_delayed or 0) > 0]

    lines = [
        f"**Invoices on record with this buyer:** {len(history)}  ",
        f"**Settled invoices:** {len(settled)}  ",
        f"**Settled late:** {len(late)}",
    ]

    if settled:
        average = sum(p.days_delayed or 0 for p in settled) / len(settled)
        worst = max(settled, key=lambda p: p.days_delayed or 0)
        lines += [
            "  ",
            f"**Average delay across settled invoices:** {average:.1f} days  ",
            (
                f"**Longest recorded delay:** {worst.days_delayed} days "
                f"(due {format_date(worst.due_date)})"
            ),
        ]

    recent = sorted(settled, key=lambda p: p.due_date, reverse=True)[:5]
    if recent:
        lines += [
            "",
            "Most recent settled invoices:",
            "",
            "| Due date | Paid on | Days delayed | Amount |",
            "|---|---|---|---|",
            *(
                f"| {format_date(p.due_date)} "
                f"| {format_date(p.actual_payment_date) if p.actual_payment_date else '—'} "
                f"| {p.days_delayed} "
                f"| {format_inr(p.payment_amount)} |"
                for p in recent
            ),
        ]

    return "\n".join(lines)


def _proof_of_delivery_section(invoice: CanonicalInvoice) -> str:
    """Say plainly what we do not have.

    LIENRHO reads invoices, customers, and payments. It has never seen a
    delivery challan or a goods receipt, and it must not imply otherwise in a
    document headed for a tribunal.
    """
    if invoice.acceptance_date is not None:
        acceptance_note = (
            f"The accounting system records buyer acceptance of this invoice on "
            f"{format_date(invoice.acceptance_date)}, which evidences receipt but "
            f"is not itself a proof-of-delivery document."
        )
    else:
        acceptance_note = (
            "The accounting system holds no separate record of buyer acceptance for this invoice."
        )

    return f"""**Not on file.**

{acceptance_note}

Attach before filing, if available: the delivery challan or lorry receipt, the \
buyer-signed goods receipt note, and the e-way bill. LIENRHO does not hold \
delivery documentation and has not attempted to infer it."""


def _communication_section(thread: CommunicationThread | None) -> str:
    """The correspondence, quoted rather than characterised."""
    if thread is None or not thread.messages:
        return "No correspondence is on file for this invoice."

    lines = [
        f"{len(thread.messages)} messages on record. Reproduced in full, oldest first:",
        "",
        "| Date | Channel | Direction | Message |",
        "|---|---|---|---|",
    ]
    for message in sorted(thread.messages, key=lambda m: m.sent_on):
        # Pipes would break the table; a legal exhibit should not be silently
        # reflowed, so escape rather than strip.
        body = message.body.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {format_date(message.sent_on)} "
            f"| {message.channel.value.title()} "
            f"| {'From buyer' if message.direction.value == 'INBOUND' else 'To buyer'} "
            f"| {body} |"
        )

    return "\n".join(lines)


def _interest_section(
    invoice: CanonicalInvoice,
    threshold: dict,
    interest: Decimal,
    rbi_bank_rate: Decimal,
) -> str:
    annual = rbi_bank_rate * MSMED_INTEREST_MULTIPLIER
    return "\n".join(
        [
            (
                "Computed under MSMED §16 — compound interest with monthly rests at "
                "three times the RBI bank rate notified for the period."
            ),
            "",
            "| | |",
            "|---|---|",
            f"| Principal | {format_inr(invoice.invoice_amount, paise=True)} |",
            f"| Appointed day (§15) | {format_date(threshold['appointed_day'])} |",
            f"| Days overdue | {threshold['days_overdue']} |",
            f"| RBI bank rate | {rbi_bank_rate:.2%} per annum |",
            f"| Statutory multiplier (§16) | {MSMED_INTEREST_MULTIPLIER}× |",
            f"| Effective rate | {annual:.2%} per annum, compounded monthly |",
            (f"| **Statutory interest accrued** | **{format_inr(interest, paise=True)}** |"),
            (
                f"| **Total claim** | "
                f"**{format_inr(invoice.invoice_amount + interest, paise=True)}** |"
            ),
            "",
            (
                "This figure was produced by `calculate_interest()`, a deterministic "
                "function, and is reproducible from the inputs above. It was not "
                "generated by a language model (CON-05, FR-013 AC)."
            ),
            "",
            (
                "The applicable bank rate is the one notified for the period claimed. "
                "Confirm it before filing."
            ),
        ]
    )


def _required_documentation_section() -> str:
    """The checklist, with unchecked boxes for what LIENRHO cannot supply.

    Left unchecked on purpose. A pre-ticked checklist would tell the user the
    packet is complete when four of these items are things only they can obtain.
    """
    return """To be attached before filing with MSME Samadhaan (ODR):

- [ ] Udyam registration certificate
- [ ] Copy of the invoice reproduced above
- [ ] Purchase order or written work order from the buyer
- [ ] Proof of delivery or acceptance of goods/services
- [ ] Statement of account showing the outstanding balance
- [ ] Copies of the correspondence reproduced above
- [ ] Interest computation working (reproduced above)
- [ ] Board resolution or authorisation for the signatory

LIENRHO has assembled the items it holds. The unchecked boxes are documents it \
does not have access to and cannot generate."""
