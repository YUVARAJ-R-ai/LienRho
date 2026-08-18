from datetime import date

from app.agents.investigator import LLMInvestigator, RuleBasedInvestigator, render_thread
from app.agents.llm_client import MockLLMClient
from app.agents.schemas import InvestigatorFindings
from app.data.communications import THREAD_INV_1023, THREAD_INV_1042
from app.data.synthetic import AS_OF


def _inv(client, fallback=None):
    return LLMInvestigator(client=client, fallback=fallback)


# ---------------------------------------------------------------- happy path


def test_llm_investigator_returns_validated_findings():
    client = MockLLMClient(
        [
            {
                "content": (
                    '{"payment_promise": true, "promised_date": "2026-08-21", '
                    '"dispute_detected": false, "confidence": 0.9, '
                    '"evidence": ["We will clear this by Friday, payment is in process."]}'
                )
            }
        ]
    )
    findings = _inv(client).investigate(THREAD_INV_1023, as_of=AS_OF)

    assert isinstance(findings, InvestigatorFindings)
    assert findings.payment_promise is True
    assert findings.promised_date == date(2026, 8, 21)
    assert findings.dispute_detected is False


def test_llm_investigator_does_not_trust_model_invented_promise_history():
    """ADR-004 discipline: reliability comes from data, not from the model."""
    client = MockLLMClient(
        [
            {
                "content": (
                    '{"payment_promise": true, "promised_date": null, '
                    '"dispute_detected": false, "confidence": 0.7, '
                    '"evidence": ["will settle"], '
                    '"promise_reliability": 0.99, "prior_broken_promises": 0}'
                )
            }
        ]
    )
    findings = _inv(client).investigate(THREAD_INV_1042, as_of=AS_OF)

    # CUST-004 has kept 0 of 3 promises — the real number must win.
    assert findings.promise_reliability == 0.0
    assert findings.prior_broken_promises == 3
    assert findings.promise_is_credible is False


def test_llm_investigator_fills_reliability_from_history_even_when_model_is_vague():
    client = MockLLMClient(
        [
            {
                "content": (
                    '{"payment_promise": true, "promised_date": null, '
                    '"dispute_detected": false, "confidence": 0.7, "evidence": []}'
                )
            }
        ]
    )
    findings = _inv(client).investigate(THREAD_INV_1042, as_of=AS_OF)

    assert findings.promise_reliability == 0.0
    assert findings.promise_is_credible is False


# ---------------------------------------------------------------- fallbacks


def test_malformed_output_falls_back_to_rule_based():
    client = MockLLMClient([{"content": "I cannot comply with that request."}])
    findings = _inv(client).investigate(THREAD_INV_1023, as_of=AS_OF)

    # The fallback reads the same thread and finds the credible promise.
    assert findings.payment_promise is True
    assert findings.promise_is_credible is True


def test_gateway_failure_falls_back_to_rule_based():
    client = MockLLMClient(fail_every=1)
    findings = _inv(client).investigate(THREAD_INV_1023, as_of=AS_OF)

    assert isinstance(findings, InvestigatorFindings)
    assert findings.payment_promise is True


def test_fallback_is_not_required_to_be_rule_based():
    """The fallback is an injected dependency, so it is swappable/testable."""
    called = []

    class SpyFallback(RuleBasedInvestigator):
        def investigate(self, thread, *, as_of):
            called.append(thread.invoice_id)
            return super().investigate(thread, as_of=as_of)

    client = MockLLMClient([{"content": "not json at all"}])
    _inv(client, fallback=SpyFallback()).investigate(THREAD_INV_1023, as_of=AS_OF)

    assert called == [THREAD_INV_1023.invoice_id]


def test_invalid_schema_falls_back():
    # Valid JSON, invalid shape (confidence out of range) — still a fallback.
    client = MockLLMClient(
        [
            {
                "content": (
                    '{"payment_promise": true, "promised_date": null, '
                    '"dispute_detected": false, "confidence": 9.9, "evidence": []}'
                )
            }
        ]
    )
    findings = _inv(client).investigate(THREAD_INV_1023, as_of=AS_OF)

    assert isinstance(findings, InvestigatorFindings)
    assert 0.0 <= findings.confidence <= 1.0


# ------------------------------------------------------------- happy + tools


def test_llm_investigator_uses_cheap_tier_and_structured_output():
    captured = {}

    class CaptureClient(MockLLMClient):
        def chat(self, *, messages, tools=None, model_tier="cheap", response_format=None):
            captured["model_tier"] = model_tier
            captured["response_format"] = response_format
            captured["tools"] = tools
            return super().chat(
                messages=messages,
                tools=tools,
                model_tier=model_tier,
                response_format=response_format,
            )

    client = CaptureClient(
        [
            {
                "content": (
                    '{"payment_promise": false, "promised_date": null, '
                    '"dispute_detected": false, "confidence": 0.5, "evidence": []}'
                )
            }
        ]
    )
    _inv(client).investigate(THREAD_INV_1023, as_of=AS_OF)

    assert captured["model_tier"] == "cheap"
    assert captured["tools"] is None
    assert captured["response_format"]["type"] == "json_schema"


def test_render_thread_marks_direction_and_orders_by_date():
    text = render_thread(THREAD_INV_1023)
    assert "customer:" in text
    assert "us:" in text
    assert "[EMAIL]" in text and "[WHATSAPP]" in text
    # The first line should be the oldest message.
    lines = text.splitlines()
    assert lines[0].startswith("2026-07-26")