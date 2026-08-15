"""Training entrypoint for the payment-delay model.

Run from backend/:
    uv run python -m app.ml_core.train

Resource flags exist because this is expected to run on a laptop that's also
running the dev servers — see --n-jobs and --cpu.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

import numpy as np

from app.data.synthetic import CUSTOMER_PROFILES, generate_dataset, sample_delay
from app.ml_core.features import (
    FEATURE_NAMES,
    bucket_for_delay,
    build_customer_stats,
    extract_features,
)
from app.ml_core.model import DelayModel, save_metrics


def build_training_matrix(seed: int = 727, n_synthetic_invoices: int = 6000):
    """Assemble (X, y) from generated payment history.

    The 30-invoice demo portfolio is far too small to train on, so this draws a
    larger sample from the same latent process (`sample_delay`) that produced
    the history. Customer statistics are computed from the *observed* payment
    history only, so no generating parameter reaches the feature matrix.
    """
    import random
    from datetime import timedelta
    from decimal import Decimal

    data = generate_dataset(seed=seed)
    stats = build_customer_stats(data.payments)
    customers = {c.customer_id: c for c in data.customers}
    profiles = {p.customer_id: p for p in CUSTOMER_PROFILES}

    rng = random.Random(seed + 1)
    rows: list[list[float]] = []
    labels: list[int] = []

    from app.canonical.models import CanonicalInvoice, PaymentStatus
    from app.data.synthetic import AS_OF

    for i in range(n_synthetic_invoices):
        profile = rng.choice(CUSTOMER_PROFILES)
        amount = Decimal(rng.randrange(30_000, 900_000, 5_000))
        # Spread issue dates across three years so seasonality is represented.
        invoice_date = AS_OF - timedelta(days=rng.randint(60, 1100))
        credit_days = rng.choice([15, 30, 30, 45, 60])
        due_date = invoice_date + timedelta(days=credit_days)

        invoice = CanonicalInvoice(
            org_id="ORG-TRAIN",
            invoice_id=f"INV-T{i:05d}",
            customer_id=profile.customer_id,
            invoice_amount=amount,
            invoice_date=invoice_date,
            due_date=due_date,
            acceptance_date=invoice_date + timedelta(days=1),
            payment_status=PaymentStatus.PAID,
            payment_date=None,
        )

        delay = sample_delay(
            profile=profiles[profile.customer_id],
            invoice_amount=amount,
            due_date=due_date,
            rng=rng,
        )

        features = extract_features(
            invoice=invoice,
            customer=customers.get(profile.customer_id),
            stats=stats.get(profile.customer_id),
        )
        rows.append([features[name] for name in FEATURE_NAMES])
        labels.append(bucket_for_delay(delay))

    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the payment-delay model")
    parser.add_argument("--seed", type=int, default=727)
    parser.add_argument("--samples", type=int, default=6000)
    parser.add_argument("--n-jobs", type=int, default=12, help="CPU threads for XGBoost")
    parser.add_argument("--cpu", action="store_true", help="Force CPU instead of CUDA")
    args = parser.parse_args()

    print(f"Building training matrix ({args.samples} samples)...", flush=True)
    X, y = build_training_matrix(seed=args.seed, n_synthetic_invoices=args.samples)

    counts = {int(c): int((y == c).sum()) for c in np.unique(y)}
    print(f"  shape={X.shape}  bucket counts={counts}", flush=True)

    device = "CPU" if args.cpu else "CUDA (falls back to CPU)"
    print(f"Training on {device} with n_jobs={args.n_jobs}...", flush=True)
    model, metrics = DelayModel.train(
        X, y, use_gpu=not args.cpu, n_jobs=args.n_jobs, seed=args.seed
    )

    model.save()
    save_metrics(metrics)

    print("\n=== Metrics (held-out) ===", flush=True)
    for key, value in asdict(metrics).items():
        print(f"  {key}: {value}", flush=True)

    gate = "PASS" if metrics.meets_nfr_005() else "FAIL"
    print(
        f"\nNFR-005 gate (ROC-AUC >= 0.75, ECE <= 0.10): {gate}",
        flush=True,
    )
    return 0 if metrics.meets_nfr_005() else 1


if __name__ == "__main__":
    sys.exit(main())
