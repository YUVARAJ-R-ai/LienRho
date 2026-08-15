# Model card — payment-delay predictor

Covers `backend/app/ml_core/`. Written so anyone asked "how do you know this number means anything" has a real answer.

## What it does

Given an open invoice, predicts a probability distribution across four delay buckets — 0–15, 16–30, 31–45, >45 days past due (FR-002). Not a binary late/on-time flag: the product's premise is predicting *when* cash arrives, and the cash forecast consumes the full distribution rather than a point estimate.

| | |
|---|---|
| Model | XGBoost, multi-class softprob, 300 trees, depth 4, lr 0.08 |
| Training | CUDA where available, automatic CPU fallback |
| Artifact | `backend/app/ml_core/artifacts/` (gitignored — regenerate with `uv run python -m app.ml_core.train`) |

## Held-out metrics

Stratified 75/25 split, 6000 samples (4500 train / 1500 test), seed 727.

| Metric | Value | NFR-005 gate |
|---|---|---|
| ROC-AUC (macro, one-vs-rest) | **0.834** | ≥ 0.75 ✅ |
| Expected calibration error | **0.031** | ≤ 0.10 ✅ |
| Bucket accuracy | 62.3% | — (25% four-class baseline) |
| Macro precision / recall / F1 | 0.615 / 0.593 / 0.599 | — |

Calibration is gated alongside discrimination on purpose. The decision engine ranks the action queue by predicted probability, so a confidently wrong model silently reorders what the user sees first — a failure the user cannot detect from the screen.

## Why the score isn't higher (and why that's the point)

The first version of the synthetic generator drew delays from a single per-customer parameter and then exposed that same parameter as the `average_delay_days` feature. Any model using it would recover our own constant and post a near-perfect score while learning nothing. The NFR-005 gate would have been unfalsifiable — measuring the generator, not the model.

Two changes fixed it:

1. **Delays come from a multi-factor latent process** (`sample_delay`): customer tendency, invoice size, Indian fiscal-year seasonality — March clears fast, April/May and the festival months run slow — plus occasional disputes producing a heavy tail no smooth feature predicts.
2. **`average_delay_days` is computed from observed payment history**, which is the only figure a real system would ever have, rather than copied from the generating parameter.

0.834 reflects a real but imperfect relationship. Two tests guard the fix: `test_customer_average_delay_is_observed_not_the_generating_parameter` and `test_delay_depends_on_more_than_the_customer_profile`. If either regresses, the metrics stop meaning anything.

See ADR-004 in [`inception.md`](inception.md).

## Features

Ten features. Two constraints govern the set: nothing may derive from the settlement date (that is the label), and every feature carries a plain-language label because FR-003 requires naming contributors in terms a user can read.

| Feature | Source |
|---|---|
| `invoice_amount_log` | Invoice |
| `credit_period_days` | Invoice (due − issue) |
| `customer_avg_delay` | Observed payment history |
| `customer_delay_volatility` | Observed payment history |
| `customer_invoice_count` | Observed payment history |
| `customer_late_rate` | Observed payment history |
| `relationship_days` | Customer record |
| `due_month` | Invoice |
| `due_is_fiscal_year_end` | Invoice (March = Indian FY end) |
| `amount_vs_customer_median` | Invoice ÷ observed history |

A customer with no payment history still produces a prediction using neutral priors — FR-002 AC-2 requires a prediction rather than an error.

## Explainability

Top three contributing features per prediction, rendered in plain language (`"Customer average delay: 58 days"`), satisfying FR-003.

**Known limitation:** this uses global gain importance, not per-prediction SHAP. It names features that matter to the model overall rather than to *this* invoice specifically, and gain importance is unsigned — so the risk direction shown on the investigation screen is inferred from the invoice's own delay probability rather than from a true per-feature sign. Chosen for inference cost against NFR-004's latency budget. Worth upgrading to SHAP if per-invoice attribution proves too coarse.

## Limitations

- **Trained on synthetic data (`ASM-02`).** No real MSME transaction history was available for this build. The generator is calibrated to plausible Indian MSME behaviour but has not been validated against real invoices. Metrics demonstrate the pipeline learns real structure; they are not a claim about field performance.
- **Eight customer profiles.** Narrow diversity relative to a real receivables book.
- **No macro effects.** No modelling of sector shocks, credit crunches, or buyer insolvency.
- **`due_month` is used directly**, so the model can only exploit seasonality it has seen; a portfolio concentrated in months absent from training will degrade.
- **Not calibrated per customer segment.** ECE is measured in aggregate; a segment could be poorly calibrated while the overall figure passes.

## Retraining

```bash
cd backend
uv run python -m app.ml_core.train              # CUDA, falls back to CPU
uv run python -m app.ml_core.train --cpu        # force CPU
uv run python -m app.ml_core.train --n-jobs 8   # cap threads
```

Exits non-zero if the NFR-005 gate fails, so it can gate CI. Metrics are written to `artifacts/metrics.json` alongside the model.

The API degrades to rule-only recommendations when no artifact exists, so a teammate who hasn't trained yet still gets a working app.
