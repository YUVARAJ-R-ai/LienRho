from datetime import date, timedelta
from decimal import Decimal

from app.agents.investigator import RuleBasedInvestigator
from app.agents.schemas import InvestigatorFindings
from app.agents.strategy import RuleBasedStrategist, StrategyContext, get_strategist
from app.agents.tools import TOOL_SCHEMAS, ToolBox
from app.data.communications import THREAD_INV_1042, THREAD_INV_1051
from app.data.synthetic import AS_OF

strategist = RuleBasedStrategist()


def _context(**overrides) -> StrategyContext:
    due = AS_OF - timedelta(days=overrides.pop("days_overdue", 20))
    base = {
        "invoice_id": "INV-T1",
        "invoice_amount": Decimal(300000),
        "due_date": due,
        "invoice_date": due - timedelta(days=30),
        "acceptance_date": due - timedelta(days=29),
        "buyer_participates_in_treds": False,
        "probability_over_45": 0.2,
        "shortfall_projected": False,
        "contributes_to_shortfall": False,
        "findings": None,
    }
    base.update(overrides)
    return StrategyContext(**base)


def _findings(**overrides) -> InvestigatorFindings:
    base = {
        "payment_promise": False,
        "dispute_detected": False,
        "confidence": 0.8,
    }
    base.update(overrides)
    return InvestigatorFindings(**base)


# ------------------------------------------------------------ tool boundary


def test_every_statutory_value_passes_through_a_recorded_tool_call():
    """The core ADR-002 guarantee, as an assertion rather than a claim."""
    result = strategist.recommend(_context(days_overdue=80), as_of=AS_OF)

    assert result.toolbox.called("check_msmed_threshold")
    assert result.toolbox.called("calculate_interest")
    assert result.statutory_interest is not None
    # The figure the recommendation rests on came out of the recorded call.
    interest_call = next(
        c for c in result.toolbox.calls if c.tool == "calculate_interest"
    )
    assert interest_call.result["interest"] == float(result.statutory_interest)


def test_interest_is_not_computed_when_there_is_no_breach():
    # Calling it anyway would put a meaningless figure in the trace.
    result = strategist.recommend(_context(days_overdue=5), as_of=AS_OF)
    assert result.statutory_flag is False
    assert result.toolbox.called("calculate_interest") is False


def test_treds_eligibility_is_always_checked_through_a_tool():
    result = strategist.recommend(_context(), as_of=AS_OF)
    assert result.toolbox.called("check_treds_eligibility")


def test_financing_terms_are_simulated_only_when_financing_is_viable():
    without = strategist.recommend(
        _context(buyer_participates_in_treds=True, shortfall_projected=False),
        as_of=AS_OF,
    )
    assert without.toolbox.called("simulate_financing") is False

    due_soon = AS_OF + timedelta(days=20)
    with_shortfall = strategist.recommend(
        _context(
            buyer_participates_in_treds=True,
            shortfall_projected=True,
            due_date=due_soon,
            invoice_date=due_soon - timedelta(days=30),
            acceptance_date=due_soon - timedelta(days=29),
        ),
        as_of=AS_OF,
    )
    assert with_shortfall.toolbox.called("simulate_financing")


def test_trace_names_the_function_and_its_result():
    result = strategist.recommend(_context(days_overdue=80), as_of=AS_OF)
    trace = " | ".join(result.trace)
    assert "check_msmed_threshold()" in trace
    assert "calculate_interest()" in trace


def test_tool_arguments_are_recorded_serializably():
    import json

    result = strategist.recommend(_context(days_overdue=80), as_of=AS_OF)
    # The record has to survive being written to an audit log.
    json.dumps([{"args": c.arguments, "result": c.result} for c in result.toolbox.calls])


def test_tool_schemas_cover_every_exposed_tool():
    box = ToolBox(as_of=AS_OF)
    exposed = {
        name
        for name in dir(box)
        if not name.startswith("_") and callable(getattr(box, name))
    } - {"trace", "called"}
    described = {s["name"] for s in TOOL_SCHEMAS}
    # Every tool an agent can call must be described to the model, or the LLM
    # implementation silently loses access to it.
    assert len(described) == len(exposed), (described, exposed)


# --------------------------------------------------------- track selection


def test_statutory_breach_escalates():
    result = strategist.recommend(_context(days_overdue=80), as_of=AS_OF)
    assert result.recommendation.action == "ESCALATE"


def test_dispute_blocks_escalation_even_past_the_threshold():
    findings = RuleBasedInvestigator().investigate(THREAD_INV_1051, as_of=AS_OF)
    result = strategist.recommend(
        _context(days_overdue=80, findings=findings), as_of=AS_OF
    )
    assert result.recommendation.action == "FOLLOW_UP"
    assert "dispute" in result.recommendation.reason.lower()


def test_broken_promise_history_is_cited_when_escalating():
    findings = RuleBasedInvestigator().investigate(THREAD_INV_1042, as_of=AS_OF)
    result = strategist.recommend(
        _context(days_overdue=80, findings=findings), as_of=AS_OF
    )
    assert result.recommendation.action == "ESCALATE"
    assert any("promise" in f.lower() for f in result.recommendation.deciding_factors)


def test_credible_promise_yields_follow_up():
    findings = _findings(
        payment_promise=True,
        promised_date=date(2026, 8, 21),
        promise_reliability=1.0,
    )
    result = strategist.recommend(
        _context(days_overdue=10, probability_over_45=0.7, findings=findings),
        as_of=AS_OF,
    )
    assert result.recommendation.action == "FOLLOW_UP"
    assert "credible" in result.recommendation.reason.lower()


def test_financing_wins_when_eligible_and_cash_is_short():
    due_soon = AS_OF + timedelta(days=20)
    result = strategist.recommend(
        _context(
            buyer_participates_in_treds=True,
            shortfall_projected=True,
            due_date=due_soon,
            invoice_date=due_soon - timedelta(days=30),
            acceptance_date=due_soon - timedelta(days=29),
        ),
        as_of=AS_OF,
    )
    assert result.recommendation.action == "FINANCE"


def test_recommendation_always_carries_deciding_factors():
    for days in (2, 20, 80):
        result = strategist.recommend(_context(days_overdue=days), as_of=AS_OF)
        assert result.recommendation.deciding_factors


def test_statutory_interest_appears_in_the_deciding_factors():
    result = strategist.recommend(_context(days_overdue=80), as_of=AS_OF)
    assert any("interest" in f.lower() for f in result.recommendation.deciding_factors)


def test_default_strategist_runs_without_an_api_key():
    assert isinstance(get_strategist(), RuleBasedStrategist)
    assert get_strategist().recommend(_context(), as_of=AS_OF).recommendation.action
