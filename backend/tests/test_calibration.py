from app.data.calibration import build_report, compute_real_stats, synthetic_assumptions
from app.data.sanitize import sanitize_portfolio
from app.ml_core.features import BUCKET_LABELS
from tests.test_sanitize import _customer, _invoice, _payment


def _payment_with_delay(days_delayed):
    p = _payment()
    return p.model_copy(update={"days_delayed": days_delayed})


# --------------------------------------------------------------- compute_real_stats


def test_empty_payment_list_returns_none_rather_than_dividing_by_zero():
    assert compute_real_stats([]) is None


def test_payments_with_no_recorded_delay_are_ignored_not_treated_as_zero():
    p = _payment().model_copy(update={"days_delayed": None})
    assert compute_real_stats([p]) is None


def test_basic_stats_match_a_hand_computed_example():
    payments = [_payment_with_delay(d) for d in (0, 10, 20, 50)]
    stats = compute_real_stats(payments)

    assert stats.n == 4
    assert stats.mean_delay_days == 20.0
    assert stats.late_rate == 0.75  # 3 of 4 have delay > 0
    assert stats.over_45_rate == 0.25  # only the 50-day one


def test_bucket_shares_sum_to_one():
    payments = [_payment_with_delay(d) for d in (2, 18, 33, 50, 5, 60)]
    stats = compute_real_stats(payments)
    assert abs(sum(stats.bucket_shares.values()) - 1.0) < 1e-9
    assert set(stats.bucket_shares) == set(BUCKET_LABELS)


def test_all_on_time_payments_have_zero_late_rate():
    payments = [_payment_with_delay(0) for _ in range(5)]
    stats = compute_real_stats(payments)
    assert stats.late_rate == 0.0
    assert stats.over_45_rate == 0.0


# ----------------------------------------------------------- synthetic_assumptions


def test_synthetic_assumptions_reflect_the_actual_customer_profiles():
    a = synthetic_assumptions()
    assert a.profile_count == 8  # CUSTOMER_PROFILES in data/synthetic.py
    assert a.min_customer_mean <= a.mean_of_customer_means <= a.max_customer_mean


# ------------------------------------------------------------------- build_report


def test_report_with_no_data_says_so_plainly():
    report = build_report(None)
    rendered = report.render()
    assert "No settled payments" in rendered


def test_report_contains_no_identifying_information():
    """The report's entire reason for existing: safe to paste into a slide."""
    payments = [_payment_with_delay(d) for d in (5, 15, 25, 50)]
    stats = compute_real_stats(payments)
    rendered = build_report(stats).render()

    # It must be pure statistics - no customer_id/name ever passed in reaches it.
    assert "ABC" not in rendered
    assert "CUST-" not in rendered  # not even a pseudonym should appear


def test_report_is_deterministic_for_the_same_stats():
    payments = [_payment_with_delay(d) for d in (5, 15, 25, 50)]
    stats = compute_real_stats(payments)
    assert build_report(stats).render() == build_report(stats).render()


def test_report_names_both_the_real_and_synthetic_figures():
    payments = [_payment_with_delay(d) for d in (5, 15, 25, 50)]
    stats = compute_real_stats(payments)
    rendered = build_report(stats).render()
    assert "Real data" in rendered
    assert "synthetic" in rendered.lower()
    assert "45 day" in rendered


# --------------------------------------------------------- full pipeline (no PII)


def test_full_pipeline_from_raw_records_to_report_leaks_nothing():
    customers = [_customer("Apex Trading", "Apex Trading")]
    invoices = [_invoice("Apex Trading")]
    payments = [_payment_with_delay(52).model_copy(update={"customer_id": "Apex Trading"})]

    sanitized = sanitize_portfolio(customers=customers, invoices=invoices, payments=payments)
    stats = compute_real_stats(sanitized.payments)
    rendered = build_report(stats).render()

    assert "Apex" not in rendered
    assert "Trading" not in rendered
    assert stats.n == 1
    assert stats.over_45_rate == 1.0
