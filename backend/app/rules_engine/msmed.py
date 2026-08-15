"""MSMED Act statutory checks (FR-005, BR-MSMED, CON-05).

Nothing in this module may call an LLM. Every value here has to be
reproducible and defensible — the escalation dossier (FR-013) is built on
these numbers, and the audit trail records which function produced each one.

Legal basis:
- Section 15 — payment is due on the "appointed day": the day after the agreed
  credit period expires, capped at 45 days from acceptance of goods/services.
- Section 16 — on delay past the appointed day the buyer owes compound interest
  with monthly rests at three times the RBI bank rate.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

# MSMED §15 caps the agreed credit period at 45 days from acceptance.
MSMED_MAX_CREDIT_DAYS = 45

# MSMED §16 sets statutory interest at three times the RBI bank rate.
MSMED_INTEREST_MULTIPLIER = Decimal(3)


def calculate_appointed_day(
    acceptance_date: date,
    agreed_credit_days: int | None = None,
) -> date:
    """The date payment became due under MSMED §15.

    The agreed credit period applies only up to the 45-day statutory cap; a
    longer contractual period does not extend the appointed day.
    """
    credit_days = (
        MSMED_MAX_CREDIT_DAYS
        if agreed_credit_days is None
        else min(agreed_credit_days, MSMED_MAX_CREDIT_DAYS)
    )
    return acceptance_date + timedelta(days=credit_days)


def days_overdue(appointed_day: date, as_of: date) -> int:
    """Days elapsed past the appointed day. Never negative."""
    return max((as_of - appointed_day).days, 0)


def check_msmed_threshold(
    *,
    acceptance_date: date,
    as_of: date,
    buyer_is_registered_enterprise: bool,
    supplier_is_msme: bool,
    agreed_credit_days: int | None = None,
) -> dict:
    """Decide whether an invoice is a statutory concern (BR-MSMED).

    The flag requires all three: the supplier is an MSME, the buyer is the kind
    of enterprise the Act binds, and payment is at least 45 days overdue.

    Boundary is inclusive — 44 days is False, 45 days is True (FR-005 AC).
    """
    appointed_day = calculate_appointed_day(acceptance_date, agreed_credit_days)
    overdue = days_overdue(appointed_day, as_of)

    buyer_conditions_met = buyer_is_registered_enterprise and supplier_is_msme
    statutory_flag = buyer_conditions_met and overdue >= MSMED_MAX_CREDIT_DAYS

    if statutory_flag:
        reason = f"{overdue} days overdue, at or past the {MSMED_MAX_CREDIT_DAYS}-day threshold"
    elif not buyer_conditions_met:
        reason = "Buyer/supplier conditions for MSMED applicability not met"
    else:
        reason = f"{overdue} days overdue, under the {MSMED_MAX_CREDIT_DAYS}-day threshold"

    return {
        "statutory_flag": statutory_flag,
        "appointed_day": appointed_day,
        "days_overdue": overdue,
        "reason": reason,
    }


def calculate_interest(
    *,
    principal: Decimal,
    appointed_day: date,
    as_of: date,
    rbi_bank_rate: Decimal,
) -> Decimal:
    """Statutory interest under MSMED §16 — compound, monthly rests.

    `rbi_bank_rate` is the annual RBI bank rate as a decimal fraction (0.0650
    for 6.50%). The caller supplies it rather than this module hardcoding it,
    because the applicable rate is the one notified for the period in question.

    Returns 0 when nothing is overdue. Result is rounded to paise.
    """
    overdue = days_overdue(appointed_day, as_of)
    if overdue <= 0 or principal <= 0:
        return Decimal("0.00")

    annual_rate = rbi_bank_rate * MSMED_INTEREST_MULTIPLIER
    monthly_rate = annual_rate / Decimal(12)

    # Monthly rests: only completed months compound. The remaining part-month
    # accrues simple interest on the compounded balance.
    whole_months = overdue // 30
    remainder_days = overdue % 30

    amount = principal * (Decimal(1) + monthly_rate) ** whole_months
    if remainder_days:
        amount += amount * monthly_rate * Decimal(remainder_days) / Decimal(30)

    interest = amount - principal
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
