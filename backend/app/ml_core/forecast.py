"""30-day rolling cash-flow forecast (FR-004, FR-015).

The forecast is *probabilistic*, not a naive "assume everything arrives on the
due date" projection. Each open invoice contributes its amount weighted by the
model's predicted probability that payment has landed by a given day — which is
the whole reason the delay model exists. A forecast that assumes on-time payment
would never surface the shortfall the product is built to warn about.

FR-015 additionally requires naming which invoices drive a projected shortfall,
ranked by contribution, so the user gets an action rather than just a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.canonical.models import BusinessFinancialState, CanonicalInvoice
from app.ml_core.features import BUCKET_EDGES, BUCKET_LABELS

FORECAST_HORIZON_DAYS = 30


@dataclass
class ForecastPoint:
    day: date
    projected_cash: Decimal
    expected_inflow_to_date: Decimal


@dataclass
class ShortfallContributor:
    """One invoice's share of responsibility for a projected shortfall."""

    invoice_id: str
    customer_id: str
    amount: Decimal
    # Amount still unlikely to have arrived by the shortfall date.
    contribution: Decimal
    probability_unpaid_by_shortfall: float


@dataclass
class CashForecast:
    points: list[ForecastPoint]
    cash_threshold: Decimal
    shortfall_date: date | None = None
    shortfall_amount: Decimal | None = None
    contributors: list[ShortfallContributor] = field(default_factory=list)

    @property
    def has_shortfall(self) -> bool:
        return self.shortfall_date is not None


def condition_on_still_unpaid(
    delay_probabilities: dict[str, float], days_overdue: int
) -> dict[str, float]:
    """Renormalize the delay distribution given the invoice is *still unpaid*.

    The model predicts delay from the due date, but an invoice sitting 20 days
    overdue has already falsified the "paid within 0-15 days" outcome. Without
    conditioning, the forecast counts that bucket's mass as incoming cash —
    money we can observe did not arrive — and systematically over-projects.

    Buckets whose window has fully elapsed are zeroed and the surviving mass is
    rescaled. If every bucket has elapsed, the invoice is treated as certain to
    fall in the open-ended >45 day bucket.
    """
    if days_overdue <= 0:
        return dict(delay_probabilities)

    survived = {}
    for edge, label in zip(BUCKET_EDGES, BUCKET_LABELS[:-1], strict=True):
        # A bucket is still possible only if its window hasn't closed yet.
        survived[label] = 0.0 if days_overdue >= edge else delay_probabilities.get(label, 0.0)
    survived[BUCKET_LABELS[-1]] = delay_probabilities.get(BUCKET_LABELS[-1], 0.0)

    total = sum(survived.values())
    if total <= 0:
        return {label: (1.0 if label == BUCKET_LABELS[-1] else 0.0) for label in BUCKET_LABELS}
    return {label: value / total for label, value in survived.items()}


def probability_paid_by(
    *,
    delay_probabilities: dict[str, float],
    due_date: date,
    target_day: date,
) -> float:
    """Probability an invoice has been paid by `target_day`.

    The model gives probability mass per delay bucket. A bucket is treated as
    fully arrived once `target_day` passes its upper edge, and the open-ended
    final bucket (>45 days) is never counted as arrived inside a 30-day horizon
    — assuming otherwise would quietly manufacture cash that may never come.
    """
    days_available = (target_day - due_date).days
    if days_available < 0:
        return 0.0

    probability = 0.0
    for edge, label in zip(BUCKET_EDGES, BUCKET_LABELS[:-1], strict=True):
        if days_available >= edge:
            probability += delay_probabilities.get(label, 0.0)
    return min(probability, 1.0)


def build_forecast(
    *,
    state: BusinessFinancialState,
    invoices: list[CanonicalInvoice],
    predictions: dict[str, dict[str, float]],
    as_of: date,
    horizon_days: int = FORECAST_HORIZON_DAYS,
) -> CashForecast:
    """Project daily cash over the horizon and locate the first shortfall.

    `predictions` maps invoice_id to that invoice's delay-bucket distribution.
    An invoice with no prediction contributes nothing — better to under-promise
    cash than to invent it.
    """
    # Expenses are spread evenly across the horizon. A real implementation would
    # use dated obligations from the connector; the canonical model only carries
    # aggregates today, so this is the honest approximation available.
    daily_expense = (state.upcoming_expenses + state.payroll + state.supplier_payments) / Decimal(
        horizon_days
    )

    points: list[ForecastPoint] = []
    shortfall_date: date | None = None
    shortfall_amount: Decimal | None = None

    for offset in range(horizon_days + 1):
        day = as_of + timedelta(days=offset)

        expected_inflow = Decimal(0)
        for invoice in invoices:
            # Condition on the invoice still being unpaid as of today, so
            # elapsed buckets don't contribute cash that never arrived.
            conditioned = condition_on_still_unpaid(
                predictions.get(invoice.invoice_id, {}),
                max((as_of - invoice.due_date).days, 0),
            )
            probability = probability_paid_by(
                delay_probabilities=conditioned,
                due_date=invoice.due_date,
                target_day=day,
            )
            expected_inflow += invoice.invoice_amount * Decimal(str(probability))

        projected = (
            state.current_cash
            + expected_inflow
            - (daily_expense * Decimal(offset))
        ).quantize(Decimal("0.01"))

        points.append(
            ForecastPoint(
                day=day,
                projected_cash=projected,
                expected_inflow_to_date=expected_inflow.quantize(Decimal("0.01")),
            )
        )

        # First crossing only — the user acts on the earliest breach.
        if shortfall_date is None and projected < state.cash_threshold:
            shortfall_date = day
            shortfall_amount = (state.cash_threshold - projected).quantize(Decimal("0.01"))

    contributors: list[ShortfallContributor] = []
    if shortfall_date is not None:
        contributors = rank_shortfall_contributors(
            invoices=invoices,
            predictions=predictions,
            shortfall_date=shortfall_date,
            as_of=as_of,
        )

    return CashForecast(
        points=points,
        cash_threshold=state.cash_threshold,
        shortfall_date=shortfall_date,
        shortfall_amount=shortfall_amount,
        contributors=contributors,
    )


def rank_shortfall_contributors(
    *,
    invoices: list[CanonicalInvoice],
    predictions: dict[str, dict[str, float]],
    shortfall_date: date,
    as_of: date,
) -> list[ShortfallContributor]:
    """Rank invoices by how much of their value is still missing at the breach (FR-015).

    Contribution is amount x probability-still-unpaid: a large invoice that will
    almost certainly arrive in time matters less than a smaller one that very
    likely won't.
    """
    contributors: list[ShortfallContributor] = []

    for invoice in invoices:
        conditioned = condition_on_still_unpaid(
            predictions.get(invoice.invoice_id, {}),
            max((as_of - invoice.due_date).days, 0),
        )
        probability_paid = probability_paid_by(
            delay_probabilities=conditioned,
            due_date=invoice.due_date,
            target_day=shortfall_date,
        )
        probability_unpaid = 1.0 - probability_paid
        if probability_unpaid <= 0:
            continue

        contributors.append(
            ShortfallContributor(
                invoice_id=invoice.invoice_id,
                customer_id=invoice.customer_id,
                amount=invoice.invoice_amount,
                contribution=(
                    invoice.invoice_amount * Decimal(str(probability_unpaid))
                ).quantize(Decimal("0.01")),
                probability_unpaid_by_shortfall=round(probability_unpaid, 4),
            )
        )

    contributors.sort(key=lambda c: c.contribution, reverse=True)
    return contributors
