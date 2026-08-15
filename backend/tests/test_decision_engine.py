from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.canonical.models import CanonicalInvoice, PaymentStatus
from app.decision_engine.engine import (
    ApprovalRequired,
    ApprovalState,
    Priority,
    RecommendedAction,
    approve,
    assert_executable,
    assign_priority,
    build_recommendation,
    decide_action,
    rank_queue,
    reject,
    score_priority,
)

AS_OF = date(2026, 8, 15)


def _invoice(invoice_id="INV-1", amount=Decimal(200000), days_overdue=20):
    due = AS_OF - timedelta(days=days_overdue)
    return CanonicalInvoice(
        org_id="ORG-TEST",
        invoice_id=invoice_id,
        customer_id="CUST-1",
        invoice_amount=amount,
        invoice_date=due - timedelta(days=30),
        due_date=due,
        acceptance_date=due - timedelta(days=29),
        payment_status=PaymentStatus.OVERDUE,
        payment_date=None,
    )


def _recommend(**overrides):
    kwargs = {
        "invoice": _invoice(),
        "customer_name": "Test Customer",
        "as_of": AS_OF,
        "delay_probabilities": {">45 days": 0.3},
        "probability_over_45": 0.3,
        "statutory_flag": False,
        "statutory_reason": "under threshold",
        "treds_eligible": False,
        "treds_reason": "buyer not a participant",
        "contributes_to_shortfall": False,
        "portfolio_max_amount": Decimal(500000),
    }
    kwargs.update(overrides)
    return build_recommendation(**kwargs)


# ------------------------------------------------------------ track selection


def test_statutory_breach_recommends_escalation():
    action, reason = decide_action(
        statutory_flag=True,
        treds_eligible=False,
        probability_over_45=0.9,
        contributes_to_shortfall=False,
    )
    assert action is RecommendedAction.ESCALATE
    assert "statutory" in reason.lower()


def test_treds_eligible_invoice_finances_when_a_shortfall_is_projected():
    action, _ = decide_action(
        statutory_flag=False,
        treds_eligible=True,
        probability_over_45=0.4,
        contributes_to_shortfall=False,
        shortfall_projected=True,
    )
    assert action is RecommendedAction.FINANCE


def test_reliable_invoice_is_a_valid_financing_candidate():
    """Financing keys off the business having a shortfall, not this invoice
    causing it. A low-risk invoice is the *best* discounting candidate."""
    action, _ = decide_action(
        statutory_flag=False,
        treds_eligible=True,
        probability_over_45=0.05,
        contributes_to_shortfall=False,
        shortfall_projected=True,
    )
    assert action is RecommendedAction.FINANCE


def test_treds_eligible_alone_does_not_trigger_financing():
    # Discounting costs money; it shouldn't be the default when cash is fine.
    action, _ = decide_action(
        statutory_flag=False,
        treds_eligible=True,
        probability_over_45=0.2,
        contributes_to_shortfall=False,
        shortfall_projected=False,
    )
    assert action is RecommendedAction.FOLLOW_UP


def test_statutory_breach_outranks_financing():
    # The legal clock is already running, so escalation wins.
    action, _ = decide_action(
        statutory_flag=True,
        treds_eligible=True,
        probability_over_45=0.9,
        contributes_to_shortfall=True,
        shortfall_projected=True,
    )
    assert action is RecommendedAction.ESCALATE


def test_dispute_blocks_escalation_and_financing():
    # A disagreement has to be resolved by a human before either action.
    action, reason = decide_action(
        statutory_flag=True,
        treds_eligible=True,
        probability_over_45=0.95,
        contributes_to_shortfall=True,
        shortfall_projected=True,
        dispute_detected=True,
    )
    assert action is RecommendedAction.FOLLOW_UP
    assert "dispute" in reason.lower()


def test_payment_promise_keeps_it_at_follow_up():
    action, reason = decide_action(
        statutory_flag=False,
        treds_eligible=False,
        probability_over_45=0.7,
        contributes_to_shortfall=False,
        payment_promise=True,
    )
    assert action is RecommendedAction.FOLLOW_UP
    assert "promised" in reason.lower()


# -------------------------------------------------------------- prioritization


def test_statutory_flag_forces_critical_regardless_of_score():
    assert (
        assign_priority(score=0.01, statutory_flag=True, contributes_to_shortfall=False)
        is Priority.CRITICAL
    )


def test_shortfall_contributor_forces_critical():
    assert (
        assign_priority(score=0.01, statutory_flag=False, contributes_to_shortfall=True)
        is Priority.CRITICAL
    )


def test_low_score_lands_in_follow_up():
    assert (
        assign_priority(score=0.1, statutory_flag=False, contributes_to_shortfall=False)
        is Priority.FOLLOW_UP
    )


def test_score_rises_with_delay_probability():
    args = {
        "invoice_amount": Decimal(200000),
        "days_overdue": 20,
        "statutory_flag": False,
        "contributes_to_shortfall": False,
        "portfolio_max_amount": Decimal(500000),
    }
    low = score_priority(probability_over_45=0.1, **args)
    high = score_priority(probability_over_45=0.9, **args)
    assert high > low


def test_score_rises_with_invoice_value():
    args = {
        "days_overdue": 20,
        "probability_over_45": 0.5,
        "statutory_flag": False,
        "contributes_to_shortfall": False,
        "portfolio_max_amount": Decimal(1000000),
    }
    small = score_priority(invoice_amount=Decimal(50000), **args)
    large = score_priority(invoice_amount=Decimal(900000), **args)
    assert large > small


def test_overdue_weight_saturates_rather_than_growing_without_bound():
    args = {
        "invoice_amount": Decimal(200000),
        "probability_over_45": 0.5,
        "statutory_flag": False,
        "contributes_to_shortfall": False,
        "portfolio_max_amount": Decimal(500000),
    }
    assert score_priority(days_overdue=60, **args) == score_priority(days_overdue=400, **args)


# --------------------------------------------------------------------- ranking


def test_queue_orders_by_tier_then_descending_value():
    items = [
        _recommend(invoice=_invoice("A", Decimal(100000))),
        _recommend(invoice=_invoice("B", Decimal(400000)), statutory_flag=True),
        _recommend(invoice=_invoice("C", Decimal(900000))),
        _recommend(invoice=_invoice("D", Decimal(200000)), statutory_flag=True),
    ]
    ranked = rank_queue(items)

    # Critical tier first, largest value within tier.
    assert [r.invoice_id for r in ranked[:2]] == ["B", "D"]
    assert all(r.priority is Priority.CRITICAL for r in ranked[:2])
    # Remaining tiers still ordered by descending value.
    rest = ranked[2:]
    assert [float(r.invoice_amount) for r in rest] == sorted(
        [float(r.invoice_amount) for r in rest], reverse=True
    )


# ------------------------------------------------------------- approval gate


def test_recommendations_start_pending_approval():
    assert _recommend().approval_state is ApprovalState.PENDING_APPROVAL


def test_finance_and_escalate_require_approval():
    finance = _recommend(treds_eligible=True, shortfall_projected=True)
    escalate = _recommend(statutory_flag=True)
    assert finance.requires_approval
    assert escalate.requires_approval


def test_executing_an_unapproved_sensitive_action_raises():
    escalate = _recommend(statutory_flag=True)
    with pytest.raises(ApprovalRequired):
        assert_executable(escalate)


def test_approved_sensitive_action_may_execute():
    escalate = approve(_recommend(statutory_flag=True), actor="owner@example.com")
    assert_executable(escalate)  # must not raise


def test_rejected_sensitive_action_still_cannot_execute():
    escalate = reject(_recommend(statutory_flag=True), actor="owner@example.com")
    with pytest.raises(ApprovalRequired):
        assert_executable(escalate)


def test_rejection_is_recorded_with_actor_and_leaves_state_unchanged():
    rec = _recommend(statutory_flag=True)
    original_action = rec.recommended_action
    reject(rec, actor="owner@example.com")

    assert rec.approval_state is ApprovalState.REJECTED
    assert rec.recommended_action == original_action
    last = rec.audit_trail[-1]
    assert last.decided_by == "HUMAN"
    assert "owner@example.com" in last.why


def test_approval_is_recorded_in_the_audit_trail():
    rec = approve(_recommend(statutory_flag=True), actor="owner@example.com")
    assert rec.audit_trail[-1].decided_by == "HUMAN"
    assert "Approved" in rec.audit_trail[-1].what


# --------------------------------------------------------------- audit trail


def test_audit_trail_names_ml_rules_and_agent_contributions():
    # NFR-007: traceable to the specific prediction and rule evaluation behind it.
    rec = _recommend(statutory_flag=True)
    actors = [e.decided_by for e in rec.audit_trail]
    assert {"ML", "RULES", "AGENT"}.issubset(set(actors))


def test_audit_trail_cites_the_deterministic_functions_by_name():
    rec = _recommend()
    rules_entry = next(e for e in rec.audit_trail if e.decided_by == "RULES")
    assert "check_msmed_threshold()" in rules_entry.why
    assert "check_treds_eligibility()" in rules_entry.why


def test_days_overdue_is_never_negative_for_a_future_due_date():
    rec = _recommend(invoice=_invoice(days_overdue=-10))
    assert rec.days_overdue == 0


# ------------------------------------------------- promise credibility (FR-007)


def test_credible_promise_softens_to_follow_up():
    action, reason = decide_action(
        statutory_flag=False,
        treds_eligible=False,
        probability_over_45=0.8,
        contributes_to_shortfall=False,
        payment_promise=True,
        promise_is_credible=True,
    )
    assert action is RecommendedAction.FOLLOW_UP
    assert "promised" in reason.lower()


def test_incredible_promise_does_not_suppress_escalation():
    """A serial defaulter's fourth promise must not buy them more time.

    This is the case the Investigator exists for: the text says "we will settle
    fully", the history says three prior promises were broken.
    """
    action, reason = decide_action(
        statutory_flag=True,
        treds_eligible=False,
        probability_over_45=0.9,
        contributes_to_shortfall=False,
        payment_promise=True,
        promise_is_credible=False,
    )
    assert action is RecommendedAction.ESCALATE
    assert "not paid" in reason.lower() or "promised before" in reason.lower()


def test_incredible_promise_falls_through_to_risk_based_follow_up():
    # No statutory breach, so it stays a follow-up — but not because of the promise.
    action, reason = decide_action(
        statutory_flag=False,
        treds_eligible=False,
        probability_over_45=0.85,
        contributes_to_shortfall=False,
        payment_promise=True,
        promise_is_credible=False,
    )
    assert action is RecommendedAction.FOLLOW_UP
    assert "promised" not in reason.lower()


def test_dispute_still_outranks_an_incredible_promise():
    action, reason = decide_action(
        statutory_flag=True,
        treds_eligible=True,
        probability_over_45=0.9,
        contributes_to_shortfall=True,
        shortfall_projected=True,
        payment_promise=True,
        promise_is_credible=False,
        dispute_detected=True,
    )
    assert action is RecommendedAction.FOLLOW_UP
    assert "dispute" in reason.lower()


def test_findings_summary_appears_in_the_audit_trail():
    rec = _recommend(findings_summary="Payment promised for 2026-08-21, no dispute on record")
    agent_entries = [e for e in rec.audit_trail if e.decided_by == "AGENT"]
    assert any("Payment promised" in e.what for e in agent_entries)
