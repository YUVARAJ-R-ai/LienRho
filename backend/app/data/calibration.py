"""Compare real payment history against the synthetic generator's assumptions
(CP4, ADR-004, ASM-02).

This deliberately does NOT retrain the model. Retraining the night before a
demo is the highest-risk move available; computing base rates from real data
and comparing them to what the generator assumes is the version that cannot
break anything, because nothing downstream of the trained model changes.

Two things this can conclude, and both are useful:

- The synthetic profiles are in the right ballpark -> say so on a slide, cite
  real numbers, move on.
- They're off -> now it's known and can be stated honestly ("real base rate is
  X%, our synthetic generator assumed Y%") instead of an unexamined guess
  standing in for validation.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.canonical.models import CanonicalPayment
from app.data.synthetic import CUSTOMER_PROFILES
from app.ml_core.features import BUCKET_LABELS, bucket_for_delay


@dataclass
class DelayStats:
    n: int
    mean_delay_days: float
    median_delay_days: float
    stdev_delay_days: float
    late_rate: float  # share with days_delayed > 0
    over_45_rate: float  # share in the open-ended bucket — NFR-005's hardest case
    bucket_shares: dict[str, float]


def compute_real_stats(payments: list[CanonicalPayment]) -> DelayStats | None:
    """Aggregate observed delays from real (sanitized) payment history.

    Returns None on an empty list rather than raising or dividing by zero —
    an empty export is a plausible outcome (wrong date range, wrong company)
    and should be reported as "no data", not crash the calibration run.
    """
    delays = [p.days_delayed for p in payments if p.days_delayed is not None]
    if not delays:
        return None

    n = len(delays)
    bucket_counts = [0, 0, 0, 0]
    for d in delays:
        bucket_counts[bucket_for_delay(d)] += 1

    return DelayStats(
        n=n,
        mean_delay_days=statistics.mean(delays),
        median_delay_days=statistics.median(delays),
        stdev_delay_days=statistics.pstdev(delays) if n > 1 else 0.0,
        late_rate=sum(1 for d in delays if d > 0) / n,
        over_45_rate=bucket_counts[3] / n,
        bucket_shares={
            label: count / n for label, count in zip(BUCKET_LABELS, bucket_counts, strict=True)
        },
    )


@dataclass
class SyntheticAssumptions:
    """What the generator's CUSTOMER_PROFILES constants imply, for comparison.

    This is a summary of assumptions baked into `data/synthetic.py`, not a
    sample of generated data — it describes the parameters the demo dataset
    was built from, which is the thing calibration is actually checking.
    """

    profile_count: int
    mean_of_customer_means: float
    min_customer_mean: float
    max_customer_mean: float


def synthetic_assumptions() -> SyntheticAssumptions:
    means = [p.mean_delay_days for p in CUSTOMER_PROFILES]
    return SyntheticAssumptions(
        profile_count=len(CUSTOMER_PROFILES),
        mean_of_customer_means=statistics.mean(means),
        min_customer_mean=min(means),
        max_customer_mean=max(means),
    )


@dataclass
class CalibrationReport:
    real: DelayStats | None
    synthetic: SyntheticAssumptions
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(self.lines)


def build_report(real: DelayStats | None) -> CalibrationReport:
    synthetic = synthetic_assumptions()
    lines = [
        "# Calibration report — real invoice history vs. synthetic assumptions",
        "",
        "Contains no customer names or identifiers — payment counts and delay",
        "statistics only. Safe to put on a slide or commit to the repo.",
        "",
    ]

    if real is None:
        lines += [
            "No settled payments with a recorded delay were found in the input.",
            "Nothing to compare — check the date range or company selection.",
        ]
        return CalibrationReport(real=real, synthetic=synthetic, lines=lines)

    lines += [
        f"## Real data ({real.n} settled payments)",
        (
            f"- Mean delay: {real.mean_delay_days:.1f} days "
            f"(median {real.median_delay_days:.1f}, stdev {real.stdev_delay_days:.1f})"
        ),
        f"- Late rate (paid after due date): {real.late_rate:.0%}",
        f"- Share in the >45 day bucket: {real.over_45_rate:.0%}",
        "- Bucket distribution:",
    ]
    for label in BUCKET_LABELS:
        lines.append(f"    {label}: {real.bucket_shares[label]:.0%}")

    lines += [
        "",
        f"## Synthetic generator's assumptions ({synthetic.profile_count} customer profiles)",
        f"- Mean of per-customer mean delays: {synthetic.mean_of_customer_means:.1f} days",
        (
            f"- Range across profiles: {synthetic.min_customer_mean:.0f}"
            f"-{synthetic.max_customer_mean:.0f} days"
        ),
        "",
        "## Reading this",
        (
            f"- Real mean ({real.mean_delay_days:.1f}d) vs. synthetic mean-of-means "
            f"({synthetic.mean_of_customer_means:.1f}d): "
            + (
                "in the same range — the generator's central tendency is plausible."
                if abs(real.mean_delay_days - synthetic.mean_of_customer_means) <= 10
                else "notably different — say so plainly rather than the number "
                "quietly not meaning what it implies."
            )
        ),
        (
            f"- Real >45 day rate ({real.over_45_rate:.0%}) is the figure closest to "
            "NFR-005's hardest bucket and worth quoting directly if asked whether "
            "the model's hardest case reflects reality."
        ),
    ]

    return CalibrationReport(real=real, synthetic=synthetic, lines=lines)
