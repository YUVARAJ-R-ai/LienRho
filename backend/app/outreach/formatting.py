"""Shared presentation helpers for generated artifacts.

These exist because a reminder, a financing submission, and a legal dossier all
quote the same rupee figure, and a figure that reads differently in each is a
figure someone has to reconcile by hand.

Nothing here computes anything — it only renders values the rules engine and
the ML layer already produced.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def format_inr(amount: Decimal | float, *, paise: bool = False) -> str:
    """Render a rupee amount with Indian digit grouping.

    Indian convention groups the last three digits, then in pairs:
    420000 → "4,20,000". Western grouping would render "420,000", which reads
    wrong to the audience these documents are addressed to.
    """
    value = Decimal(str(amount)).quantize(
        Decimal("0.01") if paise else Decimal(1), rounding=ROUND_HALF_UP
    )
    sign = "-" if value < 0 else ""
    value = abs(value)

    whole, _, fraction = str(value).partition(".")

    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        # Pairs, right to left, over everything above the last three digits.
        pairs = [head[max(i - 2, 0) : i] for i in range(len(head), 0, -2)][::-1]
        grouped = ",".join(pairs + [tail])
    else:
        grouped = whole

    rendered = f"₹{grouped}"
    if paise:
        rendered = f"{rendered}.{fraction or '00'}"
    return f"{sign}{rendered}"


def format_date(value: date) -> str:
    """Long-form date, e.g. "12 July 2026".

    Numeric dates are ambiguous across conventions, and one of these artifacts
    is a legal filing where the reading has to be unambiguous.
    """
    return f"{value.day} {value.strftime('%B %Y')}"
