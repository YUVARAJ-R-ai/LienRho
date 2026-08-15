from datetime import date, timedelta
from decimal import Decimal

from app.rules_engine.treds import check_treds_eligibility, simulate_financing

AS_OF = date(2026, 8, 15)
DUE = AS_OF + timedelta(days=30)


def _check(**overrides):
    kwargs = {
        "invoice_amount": Decimal(300000),
        "due_date": DUE,
        "as_of": AS_OF,
        "invoice_is_buyer_approved": True,
        "buyer_participates_in_treds": True,
        "supplier_is_msme": True,
    }
    kwargs.update(overrides)
    return check_treds_eligibility(**kwargs)


def test_eligible_when_all_conditions_met():
    result = _check()
    assert result["eligible"] is True
    assert result["failing_conditions"] == []


def test_ineligible_when_buyer_does_not_participate():
    result = _check(buyer_participates_in_treds=False)
    assert result["eligible"] is False
    assert "does not participate" in result["reason"]


def test_ineligible_when_invoice_not_buyer_approved():
    result = _check(invoice_is_buyer_approved=False)
    assert result["eligible"] is False
    assert any("approved by the buyer" in c for c in result["failing_conditions"])


def test_ineligible_when_supplier_not_msme():
    assert _check(supplier_is_msme=False)["eligible"] is False


def test_ineligible_when_already_financed():
    assert _check(already_financed=True)["eligible"] is False


def test_ineligible_when_due_date_too_close():
    result = _check(due_date=AS_OF + timedelta(days=2))
    assert result["eligible"] is False
    assert any("days to due date" in c for c in result["failing_conditions"])


def test_ineligible_when_invoice_already_overdue():
    result = _check(due_date=AS_OF - timedelta(days=10))
    assert result["eligible"] is False


def test_ineligible_when_below_minimum_amount():
    result = _check(invoice_amount=Decimal(10000))
    assert result["eligible"] is False
    assert any("minimum" in c for c in result["failing_conditions"])


# FR-006 AC requires the failing condition to be named, so every failure must
# be reported rather than short-circuiting at the first one.
def test_all_failing_conditions_are_reported():
    result = _check(
        invoice_amount=Decimal(1000),
        buyer_participates_in_treds=False,
        invoice_is_buyer_approved=False,
    )
    assert len(result["failing_conditions"]) == 3


def test_financing_proceeds_are_amount_less_cost():
    result = simulate_financing(
        invoice_amount=Decimal(300000),
        due_date=DUE,
        as_of=AS_OF,
        annual_discount_rate=Decimal("0.12"),
    )
    assert result["estimated_proceeds"] == result["invoice_amount"] - result["financing_cost"]


def test_financing_cost_scales_with_days_to_due():
    args = {
        "invoice_amount": Decimal(300000),
        "as_of": AS_OF,
        "annual_discount_rate": Decimal("0.12"),
    }
    short = simulate_financing(due_date=AS_OF + timedelta(days=15), **args)
    long = simulate_financing(due_date=AS_OF + timedelta(days=60), **args)
    assert long["financing_cost"] > short["financing_cost"]


def test_no_financing_cost_when_already_due():
    result = simulate_financing(
        invoice_amount=Decimal(300000),
        due_date=AS_OF - timedelta(days=5),
        as_of=AS_OF,
        annual_discount_rate=Decimal("0.12"),
    )
    assert result["financing_cost"] == Decimal("0.00")
