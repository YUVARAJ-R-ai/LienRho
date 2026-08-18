from datetime import timedelta
from decimal import Decimal

from app.agents.llm_client import FRONTIER_TIER, LiteLLMChatModel, MockLLMClient
from app.agents.schemas import InvestigatorFindings, StrategyRecommendation
from app.agents.strategy import LLMStrategist, StrategyContext
from app.agents.tools import ToolBox, build_toolbox_tools
from app.data.synthetic import AS_OF


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


# ---------------------------------------------------------------- tool loop


def test_llm_strategist_executes_tool_loop_and_grounds_the_recommendation():
    """The full ReAct loop: msmed check -> interest -> final answer."""
    due = AS_OF - timedelta(days=80)
    context = _context(days_overdue=80)
    client = MockLLMClient(
        [
            # Turn 1: the model asks for the statutory position.
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (due - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            },
            # Turn 2: now it asks for the interest figure.
            {
                "tool_calls": [
                    {
                        "name": "calculate_interest",
                        "arguments": {
                            "principal": 300000,
                            "acceptance_date": (due - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                            "rbi_bank_rate": 0.065,
                        },
                    }
                ]
            },
            # Turn 3: final structured answer.
            {
                "content": (
                    '{"action": "ESCALATE", "reason": "Statutory threshold crossed", '
                    '"deciding_factors": ["MSMED threshold crossed", '
                    '"interest Rs 5,840.07"], "confidence": 0.85}'
                )
            },
        ]
    )

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    assert result.recommendation.action == "ESCALATE"
    # The tool loop actually recorded real calls.
    assert result.toolbox.called("check_msmed_threshold")
    assert result.toolbox.called("calculate_interest")
    # The interest figure in the result comes from the tool record, not the model.
    assert result.statutory_flag is True
    assert result.statutory_interest is not None
    assert "check_msmed_threshold()" in " | ".join(result.trace)


def test_llm_strategist_finance_requires_treds_eligibility_tool():
    due_soon = AS_OF + timedelta(days=20)
    context = _context(
        buyer_participates_in_treds=True,
        shortfall_projected=True,
        due_date=due_soon,
        invoice_date=due_soon - timedelta(days=30),
        acceptance_date=due_soon - timedelta(days=29),
    )
    client = MockLLMClient(
        [
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (due_soon - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "name": "check_treds_eligibility",
                        "arguments": {
                            "invoice_amount": 300000,
                            "due_date": due_soon.isoformat(),
                            "invoice_is_buyer_approved": True,
                            "buyer_participates_in_treds": True,
                        },
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "name": "simulate_financing",
                        "arguments": {
                            "invoice_amount": 300000,
                            "due_date": due_soon.isoformat(),
                            "annual_discount_rate": 0.12,
                        },
                    }
                ]
            },
            {
                "content": (
                    '{"action": "FINANCE", "reason": "TReDS eligible, shortfall", '
                    '"deciding_factors": ["TReDS eligible"], "confidence": 0.8}'
                )
            },
        ]
    )

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    assert result.recommendation.action == "FINANCE"
    assert result.toolbox.called("check_treds_eligibility")
    assert result.toolbox.called("simulate_financing")
    assert result.treds_eligible is True


# ---------------------------------------------------------------- fallbacks


def test_ungrounded_escalate_falls_back_to_rule_based():
    """Model claims ESCALATE but never asked for the interest figure -> fallback."""
    context = _context(days_overdue=80)
    client = MockLLMClient(
        [
            {
                "content": (
                    '{"action": "ESCALATE", "reason": "Statutory threshold crossed", '
                    '"deciding_factors": ["interest Rs 5,840"], "confidence": 0.85}'
                )
            }
        ]
    )

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    # The fallback gathers the real facts and still escalates — but on its own
    # tool calls, not on the model's hallucinated figure.
    assert result.recommendation.action == "ESCALATE"
    assert result.toolbox.called("calculate_interest")
    assert result.statutory_interest is not None
    assert result.fallback_reason and "never gathered" in result.fallback_reason


def test_gateway_failure_falls_back_to_rule_based():
    context = _context(days_overdue=80)
    client = MockLLMClient(fail_every=1)

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    assert result.recommendation.action == "ESCALATE"
    assert result.toolbox.called("check_msmed_threshold")
    assert result.fallback_reason and "LLM call failed" in result.fallback_reason


def test_malformed_final_answer_falls_back_to_rule_based():
    context = _context()
    client = MockLLMClient([{"content": "I don't have enough information."}])

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    assert isinstance(result.recommendation, StrategyRecommendation)
    assert result.fallback_reason and "unparseable recommendation" in result.fallback_reason


def test_runaway_tool_loop_hits_the_step_cap_and_falls_back():
    context = _context()
    # The model keeps asking for tools forever — the cap must stop it.
    client = MockLLMClient(
        [
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (AS_OF - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            }
        ]
    )

    strategist = LLMStrategist(client=client)
    strategist._max_steps = 3
    result = strategist.recommend(context, as_of=AS_OF)

    assert isinstance(result.recommendation, StrategyRecommendation)
    assert result.fallback_reason and "runaway loop" in result.fallback_reason


def test_unknown_tool_is_reported_back_to_the_model_as_an_error():
    """The framework's ToolNode rejects unknown tools and tells the model.

    The strategist must surface this the way LangGraph does — an error
    ToolMessage — not crash the run. The model (scripted here) sees the error
    and recovers with a grounded answer.
    """
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    due = AS_OF - timedelta(days=80)
    client = MockLLMClient(
        [
            # Turn 1: the model calls a tool that doesn't exist.
            {"tool_calls": [{"name": "delete_everything", "arguments": {}}]},
            # Turn 2: it recovers by gathering the statutory facts properly.
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (due - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            },
            # Turn 3: final structured answer.
            {
                "content": (
                    '{"action": "ESCALATE", "reason": "Statutory threshold crossed", '
                    '"deciding_factors": ["MSMED threshold crossed"], '
                    '"confidence": 0.85}'
                )
            },
        ]
    )
    box = ToolBox(as_of=AS_OF)
    model = LiteLLMChatModel(client=client, model_tier=FRONTIER_TIER)
    graph = create_agent(
        model,
        tools=build_toolbox_tools(box),
        system_prompt="Use tools to gather facts, then reply with JSON.",
    )

    final = graph.invoke(
        {"messages": [HumanMessage("recommend a track for this invoice")]},
        config={"configurable": {"thread_id": "unknown-tool-test"}},
    )

    error_messages = [
        m
        for m in final["messages"]
        if isinstance(m, ToolMessage) and m.name == "delete_everything"
    ]
    assert error_messages, "the model must be told the tool does not exist"
    assert "Error" in error_messages[0].content

    last = final["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.tool_calls == []
    assert "ESCALATE" in last.content


def test_llm_strategist_uses_frontier_tier():
    captured = {}

    class CaptureClient(MockLLMClient):
        def chat(self, *, messages, tools=None, model_tier="cheap", response_format=None):
            captured["model_tier"] = model_tier
            captured["tools"] = tools
            return super().chat(
                messages=messages,
                tools=tools,
                model_tier=model_tier,
                response_format=response_format,
            )

    due = AS_OF - timedelta(days=80)
    client = CaptureClient(
        [
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (due - timedelta(days=29)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            },
            {
                "content": (
                    '{"action": "ESCALATE", "reason": "Statutory threshold crossed", '
                    '"deciding_factors": ["MSMED"], "confidence": 0.85}'
                )
            },
        ]
    )

    LLMStrategist(client=client).recommend(_context(days_overdue=80), as_of=AS_OF)

    assert captured["model_tier"] == "frontier"
    assert captured["tools"]  # the model sees TOOL_SCHEMAS


def test_interest_is_computed_only_when_the_model_asks_for_it():
    context = _context(days_overdue=80)
    client = MockLLMClient(
        [
            {
                "tool_calls": [
                    {
                        "name": "check_msmed_threshold",
                        "arguments": {
                            "acceptance_date": (AS_OF - timedelta(days=109)).isoformat(),
                            "agreed_credit_days": 30,
                        },
                    }
                ]
            },
            {
                "content": (
                    '{"action": "FOLLOW_UP", "reason": "Credible promise", '
                    '"deciding_factors": ["promise"], "confidence": 0.6}'
                )
            },
        ]
    )

    result = LLMStrategist(client=client).recommend(context, as_of=AS_OF)

    # A FOLLOW_UP that never asked for interest has no interest in its record —
    # matching the rule-based path's "don't compute meaningless figures" rule.
    assert result.toolbox.called("calculate_interest") is False