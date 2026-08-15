"""TReDS financing eligibility (FR-006, BR-TREDS, CON-05).

Deterministic, like the MSMED module — no LLM involvement.

TReDS (Trade Receivables Discounting System) lets an MSME discount an accepted
invoice to a financier for early payment. LIENRHO only ever produces a *mock*
submission (CON-07); this module decides whether an invoice would qualify.

When an invoice is ineligible the caller needs to know *which* condition failed
(FR-006 AC), so failures are returned as a list rather than a bare False.
"""

from datetime import date
from decimal import Decimal

# Discounting needs remaining tenor to price against. Past the due date there is
# nothing left to discount - that invoice is a collection problem, not a
# financing one.
MIN_DAYS_TO_DUE = 5

# Below this, discounting costs more than it returns.
MIN_INVOICE_AMOUNT = Decimal(50000)


def check_treds_eligibility(
    *,
    invoice_amount: Decimal,
    due_date: date,
    as_of: date,
    invoice_is_buyer_approved: bool,
    buyer_participates_in_treds: bool,
    supplier_is_msme: bool,
    already_financed: bool = False,
) -> dict:
    """Evaluate TReDS eligibility, naming every failing condition.

    Returns `eligible`, the list of `failing_conditions`, and a human-readable
    `reason` suitable for display on the investigation screen.
    """
    failing: list[str] = []

    if not supplier_is_msme:
        failing.append("Supplier is not a registered MSME")
    if not invoice_is_buyer_approved:
        failing.append("Invoice has not been approved by the buyer")
    if not buyer_participates_in_treds:
        failing.append("Buyer does not participate in TReDS")
    if already_financed:
        failing.append("Invoice has already been financed")

    days_to_due = (due_date - as_of).days
    if days_to_due < MIN_DAYS_TO_DUE:
        failing.append(
            f"Only {days_to_due} days to due date, minimum is {MIN_DAYS_TO_DUE}"
        )
    if invoice_amount < MIN_INVOICE_AMOUNT:
        failing.append(f"Invoice below the Rs {MIN_INVOICE_AMOUNT:,.0f} minimum")

    eligible = not failing
    return {
        "eligible": eligible,
        "failing_conditions": failing,
        "reason": "Meets all TReDS conditions" if eligible else failing[0],
    }


def simulate_financing(
    *,
    invoice_amount: Decimal,
    due_date: date,
    as_of: date,
    annual_discount_rate: Decimal,
) -> dict:
    """Mock financing terms for an eligible invoice (FR-012, CON-07).

    Simulation only — no live TReDS transaction ever occurs. The financing cost
    is the discount charged for the days between now and the due date.
    """
    days_to_due = max((due_date - as_of).days, 0)
    financing_cost = (
        invoice_amount * annual_discount_rate * Decimal(days_to_due) / Decimal(365)
    ).quantize(Decimal("0.01"))

    return {
        "invoice_amount": invoice_amount,
        "days_to_due": days_to_due,
        "annual_discount_rate": annual_discount_rate,
        "financing_cost": financing_cost,
        "estimated_proceeds": invoice_amount - financing_cost,
    }
