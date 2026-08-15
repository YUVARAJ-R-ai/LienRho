from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.rules_engine.msmed import (
    calculate_appointed_day,
    calculate_interest,
    check_msmed_threshold,
)

ACCEPTANCE = date(2026, 1, 1)
# 45 days from acceptance.
APPOINTED_DAY = date(2026, 2, 15)


def _delta(days: int) -> timedelta:
    return timedelta(days=days)


def _check(as_of: date, **overrides):
    kwargs = {
        "acceptance_date": ACCEPTANCE,
        "as_of": as_of,
        "buyer_is_registered_enterprise": True,
        "supplier_is_msme": True,
    }
    kwargs.update(overrides)
    return check_msmed_threshold(**kwargs)


def test_appointed_day_defaults_to_45_days_from_acceptance():
    assert calculate_appointed_day(ACCEPTANCE) == APPOINTED_DAY


def test_agreed_credit_period_cannot_extend_past_statutory_cap():
    # A 90-day contractual term does not override MSMED's 45-day cap.
    assert calculate_appointed_day(ACCEPTANCE, agreed_credit_days=90) == APPOINTED_DAY


def test_shorter_agreed_credit_period_is_respected():
    assert calculate_appointed_day(ACCEPTANCE, agreed_credit_days=30) == date(2026, 1, 31)


# FR-005 acceptance criterion: the boundary is inclusive at 45 days.
def test_44_days_overdue_is_not_flagged():
    result = _check(APPOINTED_DAY + _delta(44))
    assert result["days_overdue"] == 44
    assert result["statutory_flag"] is False


def test_45_days_overdue_is_flagged():
    result = _check(APPOINTED_DAY + _delta(45))
    assert result["days_overdue"] == 45
    assert result["statutory_flag"] is True


def test_not_flagged_when_buyer_conditions_fail_regardless_of_delay():
    result = _check(APPOINTED_DAY + _delta(200), buyer_is_registered_enterprise=False)
    assert result["statutory_flag"] is False
    assert "conditions" in result["reason"]


def test_not_flagged_when_supplier_is_not_msme():
    result = _check(APPOINTED_DAY + _delta(200), supplier_is_msme=False)
    assert result["statutory_flag"] is False


def test_days_overdue_never_negative_before_appointed_day():
    result = _check(date(2026, 1, 10))
    assert result["days_overdue"] == 0
    assert result["statutory_flag"] is False


def test_no_interest_before_appointed_day():
    interest = calculate_interest(
        principal=Decimal(100000),
        appointed_day=APPOINTED_DAY,
        as_of=date(2026, 2, 1),
        rbi_bank_rate=Decimal("0.065"),
    )
    assert interest == Decimal("0.00")


def test_interest_compounds_at_three_times_bank_rate():
    # 6.5% bank rate -> 19.5% statutory -> 1.625% monthly.
    # One full 30-day month on Rs 1,00,000 = Rs 1,625.
    interest = calculate_interest(
        principal=Decimal(100000),
        appointed_day=APPOINTED_DAY,
        as_of=APPOINTED_DAY + _delta(30),
        rbi_bank_rate=Decimal("0.065"),
    )
    assert interest == Decimal("1625.00")


def test_interest_grows_with_delay():
    args = {
        "principal": Decimal(100000),
        "appointed_day": APPOINTED_DAY,
        "rbi_bank_rate": Decimal("0.065"),
    }
    one_month = calculate_interest(as_of=APPOINTED_DAY + _delta(30), **args)
    six_months = calculate_interest(as_of=APPOINTED_DAY + _delta(180), **args)
    assert six_months > one_month


def test_compounding_exceeds_simple_interest_over_a_year():
    args = {
        "principal": Decimal(100000),
        "appointed_day": APPOINTED_DAY,
        "rbi_bank_rate": Decimal("0.065"),
    }
    twelve_months = calculate_interest(as_of=APPOINTED_DAY + _delta(360), **args)
    simple_equivalent = Decimal(100000) * Decimal("0.195")
    assert twelve_months > simple_equivalent


@pytest.mark.parametrize("principal", [Decimal(0), Decimal(-500)])
def test_no_interest_on_non_positive_principal(principal):
    interest = calculate_interest(
        principal=principal,
        appointed_day=APPOINTED_DAY,
        as_of=APPOINTED_DAY + _delta(90),
        rbi_bank_rate=Decimal("0.065"),
    )
    assert interest == Decimal("0.00")
