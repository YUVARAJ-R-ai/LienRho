"""Synthetic demo dataset generator (ASM-02).

No real MSME transaction history is available for this build, so the ML model
trains on generated data. Two things matter for that to be honest:

1. The portfolio has to hit the reference scenario in prd.md §37 — 30 invoices,
   Rs 42.6L total, and the three hand-built cases A/B/C that the demo narrates.
2. Payment behaviour has to be learnable *without being leaked*. Delays come
   from a multi-factor latent process (customer tendency, invoice size, fiscal
   seasonality, occasional disputes) rather than a single exposed parameter —
   see `sample_delay`. The customer's `average_delay_days` is then computed
   from observed history, exactly as a real system would derive it. The model
   therefore has to learn a real but imperfect relationship instead of
   rediscovering a constant we handed it.

Generation is seeded, so the dataset is identical across runs and machines.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean

from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
    SupplierProfile,
)

DEFAULT_SEED = 727
DEFAULT_ORG_ID = "ORG-DEMO"

# The demo is narrated as of this date; "days overdue" figures are relative to it.
AS_OF = date(2026, 8, 15)

# The business LIENRHO is running for. Real deployments read this from org
# onboarding; the dossier (FR-013) needs a named filer with a registration
# number, and refusing to invent one at generation time means having one here.
#
# The Udyam number is synthetic and follows the real format
# (UDYAM-<state>-<district>-<7 digits>) so the document renders correctly. It is
# not a live registration and must be replaced before any real filing.
DEMO_SUPPLIER = SupplierProfile(
    org_id=DEFAULT_ORG_ID,
    legal_name="Rho Precision Components Pvt Ltd",
    udyam_registration_number="UDYAM-TN-33-0042817",
    enterprise_category="Small",
    address="14/3 Ambattur Industrial Estate, Chennai 600058, Tamil Nadu",
    contact_email="accounts@rhoprecision.example",
)

# prd.md §37 fixes the portfolio total at Rs 42.6L across 30 invoices.
TARGET_TOTAL = Decimal(4260000)
TARGET_INVOICE_COUNT = 30


@dataclass(frozen=True)
class CustomerProfile:
    """A customer's payment behaviour — the signal the ML model should learn."""

    customer_id: str
    name: str
    industry: str
    customer_type: str
    # Mean/spread of how many days past due this customer actually pays.
    mean_delay_days: float
    delay_spread_days: float
    relationship_days: int
    participates_in_treds: bool
    # Some customers reply to reminders; others go quiet. Used by the agent demo.
    responsive: bool = True


CUSTOMER_PROFILES: list[CustomerProfile] = [
    CustomerProfile(
        "CUST-001", "ABC Logistics", "Logistics", "Enterprise",
        mean_delay_days=14, delay_spread_days=6, relationship_days=1460,
        participates_in_treds=False,
    ),
    CustomerProfile(
        "CUST-002", "Global Retail", "Retail", "Enterprise",
        mean_delay_days=32, delay_spread_days=9, relationship_days=900,
        participates_in_treds=True,
    ),
    CustomerProfile(
        "CUST-003", "Bharat Engineering", "Manufacturing", "SME",
        mean_delay_days=8, delay_spread_days=4, relationship_days=1100,
        participates_in_treds=False,
    ),
    CustomerProfile(
        "CUST-004", "Apex Trading", "Trading", "SME",
        mean_delay_days=48, delay_spread_days=14, relationship_days=520,
        participates_in_treds=False, responsive=False,
    ),
    CustomerProfile(
        "CUST-005", "Nova Components", "Manufacturing", "SME",
        mean_delay_days=11, delay_spread_days=5, relationship_days=760,
        participates_in_treds=True,
    ),
    CustomerProfile(
        "CUST-006", "Meridian Foods", "FMCG", "Enterprise",
        mean_delay_days=19, delay_spread_days=7, relationship_days=640,
        participates_in_treds=True,
    ),
    CustomerProfile(
        "CUST-007", "Sunrise Textiles", "Textiles", "SME",
        mean_delay_days=27, delay_spread_days=10, relationship_days=430,
        participates_in_treds=False,
    ),
    CustomerProfile(
        "CUST-008", "Kaveri Chemicals", "Chemicals", "SME",
        mean_delay_days=5, delay_spread_days=3, relationship_days=1580,
        participates_in_treds=False,
    ),
]


@dataclass
class GeneratedDataset:
    customers: list[CanonicalCustomer]
    invoices: list[CanonicalInvoice]
    payments: list[CanonicalPayment] = field(default_factory=list)

    @property
    def total_outstanding(self) -> Decimal:
        return sum(
            (i.invoice_amount for i in self.invoices if i.payment_status != PaymentStatus.PAID),
            Decimal(0),
        )


# The three cases the demo narrative walks through (prd.md §37). These are fixed
# rather than generated, because the demo depends on their exact shape.
SHOWCASE_INVOICES = [
    # Case A — relationship-preserving follow-up.
    {
        "invoice_id": "INV-1023",
        "customer_id": "CUST-001",
        "amount": Decimal(480000),
        "days_overdue": 17,
    },
    # Case B — finance via TReDS. prd.md §37 has this one *due in 10 days*
    # rather than overdue: it's the financing candidate, not a collection problem.
    {
        "invoice_id": "INV-1038",
        "customer_id": "CUST-002",
        "amount": Decimal(320000),
        "days_overdue": -10,
    },
    # Case C — statutory escalation.
    {
        "invoice_id": "INV-1042",
        "customer_id": "CUST-004",
        "amount": Decimal(210000),
        "days_overdue": 52,
    },
    # Case D — disputed. Past the statutory threshold and TReDS-eligible on
    # paper, but the customer has raised a quality objection, so neither
    # escalation nor financing is appropriate until a human resolves it. The
    # demo needs this case to show the system declining to act, not just acting.
    {
        "invoice_id": "INV-1051",
        "customer_id": "CUST-007",
        "amount": Decimal(175000),
        "days_overdue": 30,
    },
]


def generate_dataset(
    *,
    seed: int = DEFAULT_SEED,
    org_id: str = DEFAULT_ORG_ID,
    as_of: date = AS_OF,
) -> GeneratedDataset:
    """Build the full demo portfolio. Deterministic for a given seed."""
    rng = random.Random(seed)
    profiles_by_id = {p.customer_id: p for p in CUSTOMER_PROFILES}

    # History first: the customer's average delay must be *observed* from past
    # payments, not copied from the generating parameter. A real system only
    # ever has the empirical figure, and handing the model the true parameter
    # would leak the label (see sample_delay).
    payments = _build_payment_history(
        org_id=org_id, profiles=profiles_by_id, as_of=as_of, rng=rng
    )

    observed_delays: dict[str, list[int]] = {}
    for p in payments:
        observed_delays.setdefault(p.customer_id, []).append(p.days_delayed)

    customers = [
        CanonicalCustomer(
            org_id=org_id,
            customer_id=p.customer_id,
            customer_name=p.name,
            industry=p.industry,
            customer_type=p.customer_type,
            average_delay_days=(
                round(mean(observed_delays[p.customer_id]), 1)
                if observed_delays.get(p.customer_id)
                else None
            ),
            relationship_duration_days=p.relationship_days,
            treds_status="PARTICIPANT" if p.participates_in_treds else "NON_PARTICIPANT",
        )
        for p in CUSTOMER_PROFILES
    ]

    invoices = [
        _build_invoice(
            org_id=org_id,
            invoice_id=case["invoice_id"],
            customer_id=case["customer_id"],
            amount=case["amount"],
            days_overdue=case["days_overdue"],
            as_of=as_of,
        )
        for case in SHOWCASE_INVOICES
    ]

    remaining_count = TARGET_INVOICE_COUNT - len(invoices)
    remaining_total = TARGET_TOTAL - sum(i.invoice_amount for i in invoices)
    amounts = _split_amount(remaining_total, remaining_count, rng)

    for n, amount in enumerate(amounts, start=1):
        profile = rng.choice(CUSTOMER_PROFILES)
        # Age each invoice so the portfolio spans recent and long-overdue work.
        days_overdue = max(
            int(rng.gauss(profile.mean_delay_days, profile.delay_spread_days)),
            -20,
        )
        invoices.append(
            _build_invoice(
                org_id=org_id,
                invoice_id=f"INV-{1100 + n}",
                customer_id=profile.customer_id,
                amount=amount,
                days_overdue=days_overdue,
                as_of=as_of,
            )
        )

    return GeneratedDataset(customers=customers, invoices=invoices, payments=payments)


def _build_invoice(
    *,
    org_id: str,
    invoice_id: str,
    customer_id: str,
    amount: Decimal,
    days_overdue: int,
    as_of: date,
) -> CanonicalInvoice:
    """Construct an invoice whose due date sits `days_overdue` before `as_of`.

    Negative `days_overdue` means the invoice isn't due yet.
    """
    due_date = as_of - timedelta(days=days_overdue)
    invoice_date = due_date - timedelta(days=30)
    acceptance_date = invoice_date + timedelta(days=1)

    status = PaymentStatus.OVERDUE if days_overdue > 0 else PaymentStatus.PENDING

    return CanonicalInvoice(
        org_id=org_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        invoice_amount=amount,
        invoice_date=invoice_date,
        due_date=due_date,
        acceptance_date=acceptance_date,
        payment_status=status,
        payment_date=None,
    )


def sample_delay(
    *,
    profile: CustomerProfile,
    invoice_amount: Decimal,
    due_date: date,
    rng: random.Random,
) -> int:
    """Draw an actual payment delay from a multi-factor latent process.

    This deliberately does NOT simply return `gauss(profile.mean_delay_days)`.

    If the delay were drawn from a single customer parameter and that same
    parameter were then exposed as a feature, the model would just recover the
    generator and post a near-perfect ROC-AUC that means nothing — it would be
    rediscovering our own constant, not learning payment behaviour. NFR-005's
    quality gate has to be falsifiable, so the label depends on several factors
    that no single feature reveals:

    - the customer's latent tendency (partially observable via their history)
    - invoice size: larger invoices clear more slowly
    - fiscal seasonality: Indian FY ends 31 March, so March clears faster and
      April/May run slower
    - occasional disputes, which produce a heavy tail no smooth feature predicts

    The result is a genuine but imperfect relationship — the model has to work,
    and its score reflects learnable structure rather than a leaked parameter.
    """
    delay = rng.gauss(profile.mean_delay_days, profile.delay_spread_days)

    # Larger invoices need more approvals; effect grows with log of amount.
    size_factor = math.log10(max(float(invoice_amount), 1.0)) - 5.0  # ~0 at Rs 1L
    delay += size_factor * 6.0

    # Indian fiscal year ends 31 March: buyers clear dues in March, then go slow.
    if due_date.month == 3:
        delay -= 7.0
    elif due_date.month in (4, 5):
        delay += 5.0
    # Festival season (Oct-Nov) slows collections.
    elif due_date.month in (10, 11):
        delay += 4.0

    # Disputes: rare, heavy-tailed, and not predictable from the smooth features.
    if rng.random() < 0.08:
        delay += rng.uniform(25, 55)

    return max(round(delay), 0)


def _build_payment_history(
    *,
    org_id: str,
    profiles: dict[str, CustomerProfile],
    as_of: date,
    rng: random.Random,
    invoices_per_customer: int = 40,
) -> list[CanonicalPayment]:
    """Settled invoices from the past few years — the model's training set.

    Volume matters here: a few dozen rows can't support an honest train/test
    split, so this generates enough history per customer for the held-out
    evaluation NFR-005 requires.
    """
    payments: list[CanonicalPayment] = []
    counter = 0

    for profile in profiles.values():
        for n in range(invoices_per_customer):
            counter += 1
            # Spread historical invoices back across roughly three years.
            due = as_of - timedelta(days=45 + n * 26 + rng.randint(0, 20))
            amount = Decimal(rng.randrange(50_000, 500_000, 5_000))
            delay = sample_delay(
                profile=profile, invoice_amount=amount, due_date=due, rng=rng
            )
            paid_on = due + timedelta(days=delay)

            # Anything that would settle in the future hasn't happened yet.
            if paid_on >= as_of:
                continue

            payments.append(
                CanonicalPayment(
                    org_id=org_id,
                    invoice_id=f"INV-H{counter:04d}",
                    customer_id=profile.customer_id,
                    due_date=due,
                    actual_payment_date=paid_on,
                    days_delayed=delay,
                    payment_amount=amount,
                    payment_status=PaymentStatus.PAID,
                )
            )

    return payments


def _split_amount(total: Decimal, parts: int, rng: random.Random) -> list[Decimal]:
    """Split `total` into `parts` invoice-sized amounts that sum exactly to it.

    Weights are randomised so the portfolio has a realistic mix of large and
    small invoices, then the final part absorbs the rounding remainder.
    """
    weights = [rng.uniform(0.4, 2.2) for _ in range(parts)]
    weight_sum = sum(weights)

    amounts: list[Decimal] = []
    for w in weights[:-1]:
        share = (total * Decimal(str(w / weight_sum))).quantize(Decimal(1000))
        amounts.append(max(share, Decimal(25000)))

    amounts.append(total - sum(amounts))
    return amounts
