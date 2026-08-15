from datetime import date

import pytest
from pydantic import ValidationError

from app.agents.investigator import RuleBasedInvestigator, get_investigator
from app.agents.schemas import InvestigatorFindings, StrategyRecommendation
from app.data.communications import (
    THREAD_INV_1023,
    THREAD_INV_1038,
    THREAD_INV_1042,
    THREAD_INV_1047,
    THREAD_INV_1051,
    Channel,
    CommunicationThread,
    Direction,
    Message,
    build_threads,
    promise_reliability,
)
from app.data.synthetic import AS_OF, generate_dataset

investigator = RuleBasedInvestigator()


def _investigate(thread):
    return investigator.investigate(thread, as_of=AS_OF)


# ------------------------------------------------------------------- schema


def test_promised_date_without_a_promise_is_rejected():
    # A date with no promise would flow straight into the recommendation.
    with pytest.raises(ValidationError):
        InvestigatorFindings(
            payment_promise=False,
            promised_date=date(2026, 9, 1),
            dispute_detected=False,
            confidence=0.8,
        )


def test_confidence_outside_zero_to_one_is_rejected():
    with pytest.raises(ValidationError):
        InvestigatorFindings(
            payment_promise=True, dispute_detected=False, confidence=1.4
        )


def test_strategy_action_must_be_a_known_track():
    with pytest.raises(ValidationError):
        StrategyRecommendation(action="IGNORE", reason="x", confidence=0.5)

    ok = StrategyRecommendation(action="ESCALATE", reason="x", confidence=0.5)
    assert ok.action == "ESCALATE"


# --------------------------------------------------------- promise detection


def test_credible_promise_is_detected_with_its_date():
    findings = _investigate(THREAD_INV_1023)
    assert findings.payment_promise is True
    assert findings.promised_date == date(2026, 8, 21)  # "Friday", then "21st"
    assert findings.dispute_detected is False
    assert findings.promise_is_credible is True


def test_promise_from_a_serial_defaulter_is_detected_but_not_credible():
    """The case that separates this from keyword matching.

    Apex Trading's text contains a payment promise. Their history says it is
    worthless. Both facts have to survive to the recommendation.
    """
    findings = _investigate(THREAD_INV_1042)
    assert findings.payment_promise is True
    assert findings.prior_broken_promises == 3
    assert findings.promise_reliability == 0.0
    assert findings.promise_is_credible is False


def test_hedged_promise_yields_no_date():
    # "Give us 10 days" and "by month end" are not commitments to a date.
    findings = _investigate(THREAD_INV_1042)
    assert findings.promised_date is None


def test_acknowledgement_alone_is_not_a_promise():
    findings = _investigate(THREAD_INV_1038)
    assert findings.payment_promise is False
    assert findings.dispute_detected is False


def test_most_recent_position_wins():
    thread = CommunicationThread(
        invoice_id="INV-X",
        customer_id="CUST-003",
        messages=[
            Message(date(2026, 7, 1), Channel.WHATSAPP, Direction.INBOUND, "We are arranging."),
            Message(date(2026, 8, 1), Channel.WHATSAPP, Direction.INBOUND, "We will clear this."),
        ],
    )
    findings = investigator.investigate(thread, as_of=AS_OF)
    assert findings.payment_promise is True
    # The firmer, later commitment should drive confidence.
    assert findings.confidence > 0.85


def test_outbound_messages_are_not_treated_as_evidence():
    # What we said to the customer says nothing about their intent.
    thread = CommunicationThread(
        invoice_id="INV-X",
        customer_id="CUST-003",
        messages=[
            Message(
                date(2026, 8, 1), Channel.EMAIL, Direction.OUTBOUND,
                "Please confirm you will clear this by Friday.",
            )
        ],
    )
    findings = investigator.investigate(thread, as_of=AS_OF)
    assert findings.payment_promise is False


# --------------------------------------------------------- dispute detection


def test_quality_dispute_is_detected_and_summarized():
    findings = _investigate(THREAD_INV_1051)
    assert findings.dispute_detected is True
    assert findings.dispute_summary
    assert findings.confidence >= 0.85


def test_dispute_thread_is_not_read_as_a_promise():
    # "open to a partial settlement" must not register as a commitment to pay.
    findings = _investigate(THREAD_INV_1051)
    assert findings.payment_promise is False


# ------------------------------------------------------------------- silence


def test_silence_is_reported_confidently():
    thread = CommunicationThread(
        invoice_id="INV-X",
        customer_id="CUST-004",
        messages=[
            Message(date(2026, 8, 1), Channel.WHATSAPP, Direction.OUTBOUND, "Reminder."),
            Message(date(2026, 8, 5), Channel.WHATSAPP, Direction.OUTBOUND, "Reminder."),
        ],
    )
    findings = investigator.investigate(thread, as_of=AS_OF)
    assert findings.payment_promise is False
    assert findings.dispute_detected is False
    assert findings.confidence >= 0.85
    assert "No response" in findings.evidence[0]


def test_routine_thread_produces_an_unremarkable_finding():
    findings = _investigate(THREAD_INV_1047)
    assert findings.payment_promise is False
    assert findings.dispute_detected is False


# ------------------------------------------------------------------ coverage


def test_every_invoice_gets_a_thread():
    data = generate_dataset()
    threads = build_threads(data.invoices)
    assert all(i.invoice_id in threads for i in data.invoices)


def test_generated_threads_are_deterministic():
    data = generate_dataset()
    a = build_threads(data.invoices, seed=5)
    b = build_threads(data.invoices, seed=5)
    assert [m.body for m in a["INV-1108"].messages] == [
        m.body for m in b["INV-1108"].messages
    ]


def test_every_thread_investigates_without_error():
    data = generate_dataset()
    threads = build_threads(data.invoices)
    for invoice in data.invoices:
        findings = investigator.investigate(threads[invoice.invoice_id], as_of=AS_OF)
        assert 0.0 <= findings.confidence <= 1.0


def test_silent_customer_never_produces_a_promise():
    # CUST-004 has gone quiet by design; no generated thread should invent one.
    data = generate_dataset()
    threads = build_threads(data.invoices)
    for invoice in data.invoices:
        if invoice.customer_id != "CUST-004" or invoice.invoice_id == "INV-1042":
            continue
        findings = investigator.investigate(threads[invoice.invoice_id], as_of=AS_OF)
        assert findings.payment_promise is False


def test_promise_reliability_reflects_history():
    assert promise_reliability("CUST-004") == 0.0
    assert promise_reliability("CUST-001") == 1.0
    assert promise_reliability("UNKNOWN") is None


def test_default_investigator_runs_without_an_api_key():
    # The whole point of the fallback: agent findings work before OQ-02 resolves.
    assert isinstance(get_investigator(), RuleBasedInvestigator)
    assert get_investigator().investigate(THREAD_INV_1023, as_of=AS_OF).payment_promise
