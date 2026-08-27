"""Execution/outreach module (FR-011, FR-012, FR-013, issue #15).

The tests that matter most here are the refusals: the gate holding before
approval, the dossier declining to invent a proof-of-delivery, and the
submission refusing an ineligible invoice. Anyone can generate a document — the
claim this module makes is about which documents it *won't* generate.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.agents.schemas import InvestigatorFindings
from app.canonical.models import (
    CanonicalCustomer,
    CanonicalInvoice,
    CanonicalPayment,
    PaymentStatus,
)
from app.data.communications import build_threads
from app.data.synthetic import AS_OF, DEMO_SUPPLIER, generate_dataset
from app.decision_engine.engine import (
    ActionRecommendation,
    ApprovalRequired,
    ApprovalState,
    Priority,
    RecommendedAction,
    approve,
)
from app.decision_engine.service import (
    build_action_queue,
    build_artifact,
    build_draft,
    decide_on_action,
    reset_approvals,
)
from app.outreach.dossier import SECTION_TITLES, build_dossier
from app.outreach.drafts import (
    DraftChannel,
    DraftContext,
    TemplateReminderDrafter,
    get_drafter,
)
from app.outreach.formatting import format_inr
from app.outreach.treds_submission import (
    TredsIneligible,
    TredsPayload,
    TredsSimulation,
    TredsSubmission,
    build_treds_submission,
)
from tests.support import authenticated_client


@pytest.fixture(autouse=True)
def _clean_approvals():
    """Approvals are process-global, so a leaked one would silently open the gate
    for every later test."""
    reset_approvals()
    yield
    reset_approvals()


def _invoice(**overrides) -> CanonicalInvoice:
    base = {
        "org_id": "ORG-TEST",
        "invoice_id": "INV-T1",
        "customer_id": "CUST-001",
        "invoice_amount": Decimal(320000),
        "invoice_date": AS_OF - timedelta(days=90),
        "due_date": AS_OF - timedelta(days=60),
        "acceptance_date": AS_OF - timedelta(days=89),
        "payment_status": PaymentStatus.OVERDUE,
        "payment_date": None,
    }
    base.update(overrides)
    return CanonicalInvoice(**base)


def _customer(**overrides) -> CanonicalCustomer:
    base = {
        "org_id": "ORG-TEST",
        "customer_id": "CUST-001",
        "customer_name": "Apex Trading",
        "treds_status": "PARTICIPANT",
    }
    base.update(overrides)
    return CanonicalCustomer(**base)


def _recommendation(action: RecommendedAction, **overrides) -> ActionRecommendation:
    base = {
        "invoice_id": "INV-T1",
        "customer_id": "CUST-001",
        "customer_name": "Apex Trading",
        "invoice_amount": Decimal(320000),
        "days_overdue": 60,
        "priority": Priority.CRITICAL,
        "recommended_action": action,
        "reason": "test",
    }
    base.update(overrides)
    return ActionRecommendation(**base)


# ------------------------------------------------------------------ formatting


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (500, "₹500"),
        (5000, "₹5,000"),
        (420000, "₹4,20,000"),
        (4260000, "₹42,60,000"),
        (10000000, "₹1,00,00,000"),
    ],
)
def test_rupees_use_indian_digit_grouping(amount, expected):
    """Lakh/crore grouping, not thousands. These documents are read in India."""
    assert format_inr(Decimal(amount)) == expected


def test_paise_are_rendered_when_asked():
    assert format_inr(Decimal("5840.07"), paise=True) == "₹5,840.07"


# ------------------------------------------------------- FR-011 draft reminders


@pytest.fixture
def _findings_promise() -> InvestigatorFindings:
    return InvestigatorFindings(
        payment_promise=True,
        promised_date=date(2026, 8, 21),
        dispute_detected=False,
        confidence=0.85,
        promise_is_credible=True,
    )


@pytest.fixture
def _findings_unreliable() -> InvestigatorFindings:
    return InvestigatorFindings(
        payment_promise=True,
        promised_date=date(2026, 8, 21),
        dispute_detected=False,
        confidence=0.85,
        promise_is_credible=False,
        prior_broken_promises=3,
    )


@pytest.fixture
def _findings_dispute() -> InvestigatorFindings:
    return InvestigatorFindings(
        payment_promise=False,
        dispute_detected=True,
        confidence=0.9,
    )


def _draft_context(**overrides) -> DraftContext:
    base = {
        "invoice_id": "INV-T1",
        "customer_name": "Apex Trading",
        "invoice_amount": Decimal(420000),
        "due_date": date(2026, 7, 29),
        "days_overdue": 17,
        "supplier_name": DEMO_SUPPLIER.legal_name,
        "findings": None,
    }
    base.update(overrides)
    return DraftContext(**base)


@pytest.mark.parametrize("channel", list(DraftChannel))
def test_draft_references_amount_and_due_date(channel):
    """FR-011 AC: the message must reference the invoice amount and due date."""
    draft = TemplateReminderDrafter().draft(_draft_context(), channel=channel)

    assert "₹4,20,000" in draft.body
    assert "29 July 2026" in draft.body
    assert draft.invoice_id == "INV-T1"


@pytest.mark.parametrize("channel", list(DraftChannel))
def test_draft_is_always_editable(channel):
    """FR-011 AC: editable before send. Nothing sends what a human hasn't seen."""
    assert TemplateReminderDrafter().draft(_draft_context(), channel=channel).editable


def test_email_has_a_subject_and_whatsapp_does_not():
    drafter = TemplateReminderDrafter()
    email = drafter.draft(_draft_context(), channel=DraftChannel.EMAIL)
    whatsapp = drafter.draft(_draft_context(), channel=DraftChannel.WHATSAPP)

    assert email.subject and "INV-T1" in email.subject
    assert whatsapp.subject is None


def test_draft_cites_a_promised_date_found_in_correspondence(_findings_promise):
    """The point of drafting rather than typing: quote what they actually said."""
    draft = TemplateReminderDrafter().draft(
        _draft_context(findings=_findings_promise), channel=DraftChannel.EMAIL
    )
    assert "21 August 2026" in draft.body


def test_draft_does_not_accuse_a_customer_of_breaking_promises(_findings_unreliable):
    """Promise credibility is our internal assessment and stays internal.

    Putting "you have broken three promises" in a message to a customer is an
    accusation, and it is not the drafter's place to make one — the system acts
    on that judgement by escalating, not by writing it into the reminder.
    """
    draft = TemplateReminderDrafter().draft(
        _draft_context(findings=_findings_unreliable), channel=DraftChannel.EMAIL
    )
    body = draft.body.lower()
    assert "broken" not in body
    assert "unreliable" not in body
    assert "prior promise" not in body


def test_dispute_draft_asks_to_resolve_rather_than_to_pay(_findings_dispute):
    draft = TemplateReminderDrafter().draft(
        _draft_context(findings=_findings_dispute), channel=DraftChannel.WHATSAPP
    )
    assert "concern" in draft.body.lower()


def test_get_drafter_returns_the_deterministic_implementation():
    """OQ-02 is open; the template implementation is what should be wired in."""
    assert isinstance(get_drafter(), TemplateReminderDrafter)


def test_drafting_needs_no_approval():
    """A draft is what the user reads in order to decide (FR-011 vs FR-010).

    Gating it would invert the review step: they would have to approve a message
    before being allowed to read it.
    """
    assert build_draft("INV-1023") is not None


def test_draft_returns_none_for_an_unknown_invoice():
    assert build_draft("INV-DOES-NOT-EXIST") is None


# --------------------------------------------------- FR-012 mock TReDS payload


def _treds_submission(invoice=None, customer=None, approved=True) -> TredsSubmission:
    recommendation = _recommendation(RecommendedAction.FINANCE)
    if approved:
        approve(recommendation, actor="test")
    return build_treds_submission(
        recommendation=recommendation,
        invoice=invoice or _invoice(due_date=AS_OF + timedelta(days=10)),
        customer=customer or _customer(),
        as_of=AS_OF,
    )


def test_payload_carries_exactly_the_five_specified_fields():
    """FR-012 AC: the payload must match prd.md §719–725.

    A financing platform's intake schema is not ours to extend.
    """
    assert set(TredsPayload.model_fields) == {
        "invoice_id",
        "amount",
        "buyer",
        "due_date",
        "financing_required",
    }


def test_proceeds_equal_amount_minus_financing_cost():
    """FR-012 AC. The number an MSME decides to discount on."""
    submission = _treds_submission()
    assert (
        submission.simulation.estimated_proceeds
        == submission.payload.amount - submission.simulation.financing_cost
    )


def test_a_submission_that_does_not_reconcile_cannot_be_constructed():
    """Enforced on the model, so it holds for any caller, not just this one."""
    with pytest.raises(ValueError, match="estimated_proceeds"):
        TredsSubmission(
            payload=TredsPayload(
                invoice_id="INV-T1",
                amount=Decimal(320000),
                buyer="Apex Trading",
                due_date=AS_OF + timedelta(days=10),
                financing_required=True,
            ),
            simulation=TredsSimulation(
                eligible=True,
                annual_discount_rate=Decimal("0.12"),
                days_to_due=10,
                financing_cost=Decimal(1000),
                # Off by a rupee — a real discrepancy, not a rounding artifact.
                estimated_proceeds=Decimal(319001),
            ),
        )


def test_submission_is_marked_mock_and_says_so_in_the_document():
    """CON-07: never a live transaction, and the artifact must state it."""
    submission = _treds_submission()
    assert submission.mock is True
    assert "SIMULATION ONLY" in submission.to_markdown()


def test_submission_records_the_functions_that_produced_its_figures():
    """NFR-003: every financing figure traces to a named function."""
    submission = _treds_submission()
    called = " ".join(submission.tool_trace)
    assert "check_treds_eligibility()" in called
    assert "simulate_financing()" in called


def test_ineligible_invoice_is_refused_rather_than_submitted():
    """A submission that looks legitimate but cannot succeed is worse than none."""
    with pytest.raises(TredsIneligible) as exc:
        _treds_submission(customer=_customer(treds_status="NON_PARTICIPANT"))
    assert exc.value.failing_conditions


def test_submission_requires_approval_first():
    """FR-010, CON-06 — the gate, before anything is assembled."""
    with pytest.raises(ApprovalRequired):
        _treds_submission(approved=False)


# ----------------------------------------------------- FR-013 escalation dossier


def _dossier(approved=True, payments=None, thread=None, invoice=None):
    recommendation = _recommendation(RecommendedAction.ESCALATE)
    if approved:
        approve(recommendation, actor="test")
    return build_dossier(
        recommendation=recommendation,
        invoice=invoice or _invoice(),
        customer=_customer(),
        supplier=DEMO_SUPPLIER,
        payments=payments if payments is not None else [],
        thread=thread,
        as_of=AS_OF,
    )


def test_dossier_contains_every_section_fr_013_names():
    """FR-013 AC: all listed sections present. None is dropped when data is thin."""
    dossier = _dossier()
    assert [s.title for s in dossier.sections] == list(SECTION_TITLES)


def test_statutory_interest_comes_from_the_deterministic_function():
    """FR-013 AC + CON-05: `calculate_interest()`, never a language model."""
    dossier = _dossier()
    assert any("calculate_interest()" in call for call in dossier.tool_trace)
    assert dossier.statutory_interest > 0
    assert "calculate_interest()" in dossier.to_markdown()


def test_total_claim_is_principal_plus_interest():
    dossier = _dossier()
    invoice = _invoice()
    assert dossier.total_claim == invoice.invoice_amount + dossier.statutory_interest


def test_dossier_states_that_proof_of_delivery_is_missing():
    """It must not imply a document it has never seen.

    Fabricating a delivery reference in a filing would be the worst thing this
    system could do, so absence is reported as absence.
    """
    body = next(s.body for s in _dossier().sections if s.title == "Proof of delivery")
    assert "Not on file" in body


def test_required_documentation_is_left_unchecked():
    """A pre-ticked checklist would claim a completeness LIENRHO cannot deliver."""
    body = next(
        s.body for s in _dossier().sections if s.title == "Required documentation"
    )
    assert "- [ ]" in body
    assert "- [x]" not in body


def test_dossier_says_it_is_not_filed_automatically():
    """CON-08 — stated inside the artifact, where it actually travels."""
    assert "MANUAL FILING" in _dossier().to_markdown()


def test_payment_history_reports_absence_rather_than_implying_a_pattern():
    body = next(s.body for s in _dossier().sections if s.title == "Payment history")
    assert "No prior settled invoices" in body


def test_payment_history_summarises_prior_conduct_when_it_exists():
    payments = [
        CanonicalPayment(
            org_id="ORG-TEST",
            invoice_id=f"INV-H{i}",
            customer_id="CUST-001",
            due_date=AS_OF - timedelta(days=200 + i * 30),
            actual_payment_date=AS_OF - timedelta(days=150 + i * 30),
            days_delayed=50,
            payment_amount=Decimal(100000),
            payment_status=PaymentStatus.PAID,
        )
        for i in range(3)
    ]
    body = next(
        s.body for s in _dossier(payments=payments).sections if s.title == "Payment history"
    )
    assert "**Settled late:** 3" in body
    assert "50.0 days" in body


def test_communication_evidence_quotes_the_thread_verbatim():
    """A legal exhibit is quoted, not characterised."""
    thread = build_threads(generate_dataset().invoices)["INV-1042"]
    body = next(
        s.body
        for s in _dossier(thread=thread).sections
        if s.title == "Communication evidence"
    )
    assert "we will settle fully" in body


def test_dossier_requires_approval_first():
    """FR-010, CON-06 — no legal document exists before a human says so."""
    with pytest.raises(ApprovalRequired):
        _dossier(approved=False)


# ----------------------------------------------------------- the approval gate


def test_queue_items_start_pending_approval():
    assert all(
        r.approval_state is ApprovalState.PENDING_APPROVAL for r in build_action_queue()
    )


def test_approval_survives_a_queue_rebuild():
    """The queue is derived on every request; the human decision must not be."""
    decide_on_action("INV-1042", approved=True, actor="tester")
    rebuilt = {r.invoice_id: r for r in build_action_queue()}
    assert rebuilt["INV-1042"].approval_state is ApprovalState.APPROVED


def test_rejection_is_recorded_and_leaves_other_invoices_alone():
    """FR-010 AC-2: rejecting changes nothing but the recorded decision."""
    decide_on_action("INV-1042", approved=False, actor="tester")
    rebuilt = {r.invoice_id: r for r in build_action_queue()}
    assert rebuilt["INV-1042"].approval_state is ApprovalState.REJECTED
    assert rebuilt["INV-1023"].approval_state is ApprovalState.PENDING_APPROVAL


def test_both_decisions_stay_on_the_audit_trail():
    """FR-014: who decided what, in order — not just the latest state."""
    decide_on_action("INV-1042", approved=True, actor="first")
    recommendation = decide_on_action("INV-1042", approved=False, actor="second")
    human = [e for e in recommendation.audit_trail if e.decided_by == "HUMAN"]
    assert [e.why for e in human] == [
        "Approved by first",
        "Rejected by second — invoice state unchanged",
    ]


def test_deciding_on_an_unknown_invoice_returns_none():
    assert decide_on_action("INV-NOPE", approved=True, actor="tester") is None


def test_build_artifact_dispatches_on_the_recommended_action():
    """A caller cannot ask for a dossier on an invoice the system said to remind."""
    for invoice_id, expected in (
        ("INV-1042", "EscalationDossier"),
        ("INV-1038", "TredsSubmission"),
        ("INV-1023", "ReminderDraft"),
    ):
        recommendation = decide_on_action(invoice_id, approved=True, actor="tester")
        artifact = build_artifact(recommendation)
        assert type(artifact).__name__ == expected


# ------------------------------------------------------------------ API surface

# Every /api route requires a bearer token now (#20); this client carries one.
client = authenticated_client()


def test_draft_endpoint_returns_a_reminder():
    response = client.get("/api/invoice/INV-1023/draft?channel=WHATSAPP")
    assert response.status_code == 200
    assert response.json()["kind"] == "REMINDER"
    assert response.json()["editable"] is True


def test_draft_endpoint_404s_for_an_unknown_invoice():
    assert client.get("/api/invoice/INV-NOPE/draft").status_code == 404


def test_approve_endpoint_returns_the_generated_artifact():
    body = client.post("/api/actions/INV-1042/approve?actor=tester").json()
    assert body["approvalState"] == "APPROVED"
    assert body["artifact"]["kind"] == "DOSSIER"
    assert "MANUAL FILING" in body["artifact"]["contentMarkdown"]


def test_finance_approval_returns_the_machine_readable_payload():
    """The one artifact a downstream system would consume."""
    body = client.post("/api/actions/INV-1038/approve").json()
    assert body["artifact"]["kind"] == "TREDS_SUBMISSION"
    assert set(body["artifact"]["payload"]) == {
        "invoice_id",
        "amount",
        "buyer",
        "due_date",
        "financing_required",
    }


def test_reject_endpoint_withholds_the_artifact():
    """Refusing an action must not hand back what it would have produced."""
    body = client.post("/api/actions/INV-1042/reject?actor=tester").json()
    assert body["approvalState"] == "REJECTED"
    assert body["artifact"] is None


def test_decision_endpoints_404_for_an_unknown_invoice():
    assert client.post("/api/actions/INV-NOPE/approve").status_code == 404
    assert client.post("/api/actions/INV-NOPE/reject").status_code == 404


def test_artifact_endpoint_refuses_before_approval():
    """Re-reading a decision must not be a way around making one."""
    assert client.get("/api/invoice/INV-1042/artifact").status_code == 409


def test_artifact_endpoint_returns_the_document_after_approval():
    """An approved dossier has to survive a page reload — it is meant to be filed."""
    client.post("/api/actions/INV-1042/approve?actor=tester")
    response = client.get("/api/invoice/INV-1042/artifact")
    assert response.status_code == 200
    assert response.json()["kind"] == "DOSSIER"


def test_artifact_endpoint_404s_for_an_unknown_invoice():
    assert client.get("/api/invoice/INV-NOPE/artifact").status_code == 404
