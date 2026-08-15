import math
import random
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.canonical.models import CanonicalInvoice, PaymentStatus
from app.data.synthetic import CUSTOMER_PROFILES, generate_dataset, sample_delay
from app.ml_core.features import (
    BUCKET_LABELS,
    FEATURE_NAMES,
    bucket_for_delay,
    build_customer_stats,
    describe_feature,
    extract_features,
)
from app.ml_core.model import expected_calibration_error


def _invoice(**overrides) -> CanonicalInvoice:
    base = {
        "org_id": "ORG-TEST",
        "invoice_id": "INV-T1",
        "customer_id": "CUST-001",
        "invoice_amount": Decimal(200000),
        "invoice_date": date(2026, 6, 1),
        "due_date": date(2026, 7, 1),
        "acceptance_date": date(2026, 6, 2),
        "payment_status": PaymentStatus.OVERDUE,
        "payment_date": None,
    }
    base.update(overrides)
    return CanonicalInvoice(**base)


# --------------------------------------------------------------------- buckets


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, 0), (15, 0), (16, 1), (30, 1), (31, 2), (45, 2), (46, 3), (200, 3)],
)
def test_delay_maps_to_correct_bucket(days, expected):
    assert bucket_for_delay(days) == expected


def test_there_are_four_buckets():
    assert len(BUCKET_LABELS) == 4


# -------------------------------------------------------------------- features


def test_feature_vector_covers_every_declared_feature():
    data = generate_dataset()
    stats = build_customer_stats(data.payments)
    customer = data.customers[0]

    features = extract_features(
        invoice=_invoice(customer_id=customer.customer_id),
        customer=customer,
        stats=stats.get(customer.customer_id),
    )
    assert set(features) == set(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in features.values())


# FR-002 AC-2: a customer with no history must still get a prediction.
def test_features_are_produced_for_a_customer_with_no_history():
    features = extract_features(invoice=_invoice(), customer=None, stats=None)
    assert set(features) == set(FEATURE_NAMES)
    assert not any(math.isnan(v) for v in features.values())


def test_customer_stats_are_computed_from_settled_payments():
    data = generate_dataset()
    stats = build_customer_stats(data.payments)

    assert stats
    for s in stats.values():
        assert s.invoice_count > 0
        assert 0.0 <= s.late_rate <= 1.0
        assert s.delay_volatility >= 0.0


# FR-003: explanations must read as plain language, not raw column names.
def test_feature_descriptions_are_human_readable():
    assert "Rs " in describe_feature("invoice_amount_log", 5.3)
    assert "%" in describe_feature("customer_late_rate", 0.42)
    assert describe_feature("due_is_fiscal_year_end", 1.0).endswith("yes")
    assert "March" in describe_feature("due_month", 3.0)


# --------------------------------------------------------------- label leakage


def test_customer_average_delay_is_observed_not_the_generating_parameter():
    """Guards the de-circularization.

    `average_delay_days` must be the empirical mean of generated history, not
    the profile constant used to draw the delays. If these ever match exactly
    the model is being handed its own label and NFR-005 stops being meaningful.
    """
    data = generate_dataset()
    profiles = {p.customer_id: p for p in CUSTOMER_PROFILES}

    exact_matches = sum(
        1
        for c in data.customers
        if c.average_delay_days == profiles[c.customer_id].mean_delay_days
    )
    assert exact_matches == 0


def test_delay_depends_on_more_than_the_customer_profile():
    """A single customer's delays must vary with invoice-level factors.

    If delay were a pure function of the customer, a model given customer
    identity would be perfect and the metrics would be theatre.
    """
    profile = CUSTOMER_PROFILES[0]
    rng = random.Random(0)

    small = [
        sample_delay(
            profile=profile,
            invoice_amount=Decimal(50000),
            due_date=date(2026, 3, 15),
            rng=rng,
        )
        for _ in range(300)
    ]
    large = [
        sample_delay(
            profile=profile,
            invoice_amount=Decimal(800000),
            due_date=date(2026, 11, 15),
            rng=rng,
        )
        for _ in range(300)
    ]
    # Bigger invoices in a slow month should clear later than small ones at
    # fiscal year-end, for the same customer.
    assert sum(large) / len(large) > sum(small) / len(small)


def test_fiscal_year_end_clears_faster_than_the_months_after_it():
    profile = CUSTOMER_PROFILES[1]
    rng = random.Random(7)
    amount = Decimal(200000)

    march = [
        sample_delay(profile=profile, invoice_amount=amount, due_date=date(2026, 3, 10), rng=rng)
        for _ in range(400)
    ]
    april = [
        sample_delay(profile=profile, invoice_amount=amount, due_date=date(2026, 4, 10), rng=rng)
        for _ in range(400)
    ]
    assert sum(march) / len(march) < sum(april) / len(april)


# ----------------------------------------------------------------- calibration


def test_perfectly_calibrated_predictions_score_near_zero_ece():
    # Confident and always right -> confidence matches accuracy -> ECE ~ 0.
    y = np.array([0, 1, 2, 3] * 25)
    probs = np.zeros((len(y), 4))
    probs[np.arange(len(y)), y] = 1.0
    assert expected_calibration_error(y, probs) < 0.01


def test_confidently_wrong_predictions_score_high_ece():
    y = np.zeros(100, dtype=int)
    probs = np.zeros((100, 4))
    probs[:, 1] = 1.0  # always certain, always wrong
    assert expected_calibration_error(y, probs) > 0.9


# ------------------------------------------------------------------ end-to-end


def test_trained_model_predicts_and_explains(tmp_path):
    """Train small and confirm the prediction contract holds (FR-002, FR-003)."""
    from app.ml_core.model import DelayModel
    from app.ml_core.train import build_training_matrix

    X, y = build_training_matrix(seed=5, n_synthetic_invoices=800)
    # CPU keeps the test runnable in CI, which has no GPU.
    model, metrics = DelayModel.train(X, y, use_gpu=False, n_jobs=2, seed=5)

    assert metrics.n_train + metrics.n_test == 800

    data = generate_dataset()
    stats = build_customer_stats(data.payments)
    customer = data.customers[0]
    features = extract_features(
        invoice=_invoice(customer_id=customer.customer_id),
        customer=customer,
        stats=stats.get(customer.customer_id),
    )
    prediction = model.predict(features)

    # FR-002 AC-1: the four bucket probabilities sum to 1.0 +/- 0.01.
    assert abs(sum(prediction.probabilities.values()) - 1.0) < 0.01
    assert set(prediction.probabilities) == set(BUCKET_LABELS)
    assert prediction.expected_bucket in BUCKET_LABELS

    # FR-003: at least three named contributing factors, in plain language.
    assert len(prediction.top_factors) >= 3
    assert all(":" in f["description"] for f in prediction.top_factors)


def test_model_roundtrips_through_disk(tmp_path):
    from app.ml_core.model import DelayModel
    from app.ml_core.train import build_training_matrix

    X, y = build_training_matrix(seed=3, n_synthetic_invoices=500)
    model, _ = DelayModel.train(X, y, use_gpu=False, n_jobs=2, seed=3)

    path = tmp_path / "model.json"
    model.save(path)
    reloaded = DelayModel.load(path)

    features = extract_features(invoice=_invoice(), customer=None, stats=None)
    assert reloaded.predict(features).probabilities == model.predict(features).probabilities


def test_invoice_dates_used_by_features_are_available_before_payment():
    """No feature may derive from the settlement date — that's the label."""
    invoice = _invoice(payment_date=date(2026, 8, 1))
    without = extract_features(invoice=_invoice(payment_date=None), customer=None, stats=None)
    with_payment = extract_features(invoice=invoice, customer=None, stats=None)
    assert without == with_payment


def test_unpaid_invoice_features_do_not_need_a_delay(tmp_path):
    invoice = _invoice(payment_status=PaymentStatus.PENDING, due_date=date(2026, 12, 1))
    features = extract_features(invoice=invoice, customer=None, stats=None)
    assert features["credit_period_days"] == (
        invoice.due_date - invoice.invoice_date
    ).days


def test_training_matrix_shape_matches_feature_count():
    from app.ml_core.train import build_training_matrix

    X, y = build_training_matrix(seed=11, n_synthetic_invoices=200)
    assert X.shape == (200, len(FEATURE_NAMES))
    assert len(y) == 200
    assert set(np.unique(y)).issubset({0, 1, 2, 3})


def test_all_four_buckets_are_represented_in_training_data():
    from app.ml_core.train import build_training_matrix

    _, y = build_training_matrix(seed=13, n_synthetic_invoices=2000)
    # A bucket with no examples can't be learned or evaluated.
    assert set(np.unique(y)) == {0, 1, 2, 3}


def test_relationship_length_feature_reads_from_the_customer():
    data = generate_dataset()
    customer = data.customers[0]
    features = extract_features(invoice=_invoice(), customer=customer, stats=None)
    assert features["relationship_days"] == float(customer.relationship_duration_days)


def test_seasonality_feature_flags_march():
    march = extract_features(
        invoice=_invoice(invoice_date=date(2026, 2, 1), due_date=date(2026, 3, 3)),
        customer=None,
        stats=None,
    )
    july = extract_features(invoice=_invoice(), customer=None, stats=None)
    assert march["due_is_fiscal_year_end"] == 1.0
    assert july["due_is_fiscal_year_end"] == 0.0


def test_larger_invoice_produces_larger_size_feature():
    small = extract_features(
        invoice=_invoice(invoice_amount=Decimal(50000)), customer=None, stats=None
    )
    large = extract_features(
        invoice=_invoice(invoice_amount=Decimal(900000)), customer=None, stats=None
    )
    assert large["invoice_amount_log"] > small["invoice_amount_log"]


def test_payment_history_spans_enough_rows_to_train_on():
    data = generate_dataset()
    # A held-out split needs meaningful volume; a few dozen rows can't support it.
    assert len(data.payments) >= 200


def test_generated_delays_are_never_negative():
    rng = random.Random(1)
    profile = CUSTOMER_PROFILES[7]  # fastest payer
    delays = [
        sample_delay(
            profile=profile,
            invoice_amount=Decimal(30000),
            due_date=date(2026, 3, 1) + timedelta(days=i),
            rng=rng,
        )
        for i in range(200)
    ]
    assert min(delays) >= 0
