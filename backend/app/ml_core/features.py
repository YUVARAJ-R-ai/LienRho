"""Feature engineering for the payment-delay model (FR-002).

Two rules govern what may appear here:

1. **No leakage.** Every feature must be computable at scoring time, from
   information available *before* the invoice is paid. Anything derived from
   the settlement date is the label, not a feature.
2. **Explainable.** FR-003 requires naming the top contributing features in
   plain language, so each feature carries a human-readable label rather than
   being an anonymous column.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from app.canonical.models import CanonicalCustomer, CanonicalInvoice

# Delay buckets from prd.md §9 / FR-002.
BUCKET_EDGES = [15, 30, 45]
BUCKET_LABELS = ["0-15 days", "16-30 days", "31-45 days", ">45 days"]


def bucket_for_delay(days_delayed: int) -> int:
    """Map an actual delay to its bucket index (0-3)."""
    for i, edge in enumerate(BUCKET_EDGES):
        if days_delayed <= edge:
            return i
    return len(BUCKET_EDGES)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    # Shown to the user in explanations, so it has to read as plain English.
    label: str
    # How to phrase the value in an explanation, e.g. "27 days".
    unit: str = ""


FEATURE_SPECS: list[FeatureSpec] = [
    FeatureSpec("invoice_amount_log", "Invoice size", ""),
    FeatureSpec("credit_period_days", "Agreed credit period", "days"),
    FeatureSpec("customer_avg_delay", "Customer average delay", "days"),
    FeatureSpec("customer_delay_volatility", "Customer consistency", "days"),
    FeatureSpec("customer_invoice_count", "Invoices with this customer", ""),
    FeatureSpec("relationship_days", "Relationship length", "days"),
    FeatureSpec("customer_late_rate", "Share of past invoices paid late", ""),
    FeatureSpec("due_month", "Due month", ""),
    FeatureSpec("due_is_fiscal_year_end", "Falls in fiscal year-end month", ""),
    FeatureSpec("amount_vs_customer_median", "Size vs this customer's usual", "x"),
]

FEATURE_NAMES = [f.name for f in FEATURE_SPECS]


@dataclass
class CustomerStats:
    """Payment behaviour observed from a customer's settled invoices.

    Computed from history only — never from the invoice being scored.
    """

    avg_delay: float
    delay_volatility: float
    invoice_count: int
    late_rate: float
    median_amount: float


def build_customer_stats(payments) -> dict[str, CustomerStats]:
    """Aggregate settled payments into per-customer behaviour statistics."""
    by_customer: dict[str, list] = {}
    for p in payments:
        if p.days_delayed is None:
            continue
        by_customer.setdefault(p.customer_id, []).append(p)

    stats: dict[str, CustomerStats] = {}
    for customer_id, rows in by_customer.items():
        delays = [r.days_delayed for r in rows]
        amounts = sorted(float(r.payment_amount) for r in rows)
        n = len(delays)
        avg = sum(delays) / n
        variance = sum((d - avg) ** 2 for d in delays) / n if n > 1 else 0.0

        stats[customer_id] = CustomerStats(
            avg_delay=avg,
            delay_volatility=math.sqrt(variance),
            invoice_count=n,
            late_rate=sum(1 for d in delays if d > 0) / n,
            median_amount=amounts[n // 2],
        )
    return stats


# Fallback for a customer with no payment history at all. FR-002's acceptance
# criteria require a prediction rather than an error in that case, so these are
# deliberately neutral rather than optimistic.
_NO_HISTORY = CustomerStats(
    avg_delay=20.0,
    delay_volatility=15.0,
    invoice_count=0,
    late_rate=0.5,
    median_amount=100_000.0,
)


def extract_features(
    *,
    invoice: CanonicalInvoice,
    customer: CanonicalCustomer | None,
    stats: CustomerStats | None,
) -> dict[str, float]:
    """Build the feature vector for one invoice.

    `stats` is None for a customer we've never been paid by; the model still
    has to return a prediction (FR-002 AC-2), so neutral priors stand in.
    """
    s = stats or _NO_HISTORY
    amount = float(invoice.invoice_amount)
    credit_period = (invoice.due_date - invoice.invoice_date).days

    return {
        "invoice_amount_log": math.log10(max(amount, 1.0)),
        "credit_period_days": float(credit_period),
        "customer_avg_delay": s.avg_delay,
        "customer_delay_volatility": s.delay_volatility,
        "customer_invoice_count": float(s.invoice_count),
        "relationship_days": float(
            customer.relationship_duration_days if customer and customer.relationship_duration_days else 0
        ),
        "customer_late_rate": s.late_rate,
        "due_month": float(invoice.due_date.month),
        "due_is_fiscal_year_end": 1.0 if invoice.due_date.month == 3 else 0.0,
        "amount_vs_customer_median": amount / max(s.median_amount, 1.0),
    }


def describe_feature(name: str, value: float) -> str:
    """Render one feature as plain language for an explanation (FR-003)."""
    spec = next((f for f in FEATURE_SPECS if f.name == name), None)
    if spec is None:
        return f"{name}: {value:.2f}"

    if name == "invoice_amount_log":
        return f"{spec.label}: Rs {10 ** value:,.0f}"
    if name == "customer_late_rate":
        return f"{spec.label}: {value:.0%}"
    if name == "due_is_fiscal_year_end":
        return f"{spec.label}: {'yes' if value else 'no'}"
    if name == "amount_vs_customer_median":
        return f"{spec.label}: {value:.1f}x"
    if name == "due_month":
        return f"{spec.label}: {date(2000, int(value), 1):%B}"
    if spec.unit:
        return f"{spec.label}: {value:.0f} {spec.unit}"
    return f"{spec.label}: {value:.2f}"
