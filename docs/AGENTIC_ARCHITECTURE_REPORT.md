# LIENRHO Agentic Architecture — Implementation Report

> **Scope**: Complete inventory of agent-related code, data flows, and atomic functionalities needed to implement production LLM agents (unblocking OQ-02).

---

## 1. Executive Summary

LIENRHO implements **two agents today** (Investigator, Strategy) with a **third planned** (Execution). All current agents are **deterministic rule-based implementations** that serve as production fallbacks. LLM-backed versions (`LLMInvestigator`, `LLMStrategist`) are stubbed behind identical interfaces, blocked only on **OQ-02** (LLM provider/key selection).

**Key Architectural Principle**: The LLM never computes statutory, financial, or interest values (CON-05, ADR-002, NFR-003). Agents call deterministic tools via `ToolBox`; every call is recorded for audit. The Decision Engine cannot distinguish LLM vs rule-based output — both validate against the same Pydantic schemas.

---

## 2. Agent Inventory

### 2.1 Receivables Investigator (FR-007)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Read customer correspondence for one invoice; extract structured findings |
| **File** | `backend/app/agents/investigator.py` |
| **Interface** | `Investigator` (ABC) → `investigate(thread: CommunicationThread, as_of: date) → InvestigatorFindings` |
| **Implementations** | `RuleBasedInvestigator` (production), `LLMInvestigator` (stub, OQ-02) |
| **Factory** | `get_investigator()` → returns rule-based while OQ-02 open |
| **Output Schema** | `InvestigatorFindings` (Pydantic, `schemas.py:20-71`) |

**Findings Structure**:
```python
payment_promise: bool              # Explicit commitment to pay
promised_date: date | None         # Specific date if stated (null if vague)
dispute_detected: bool             # Quality/qty/billing dispute raised
confidence: float                  # 0-1 confidence in reading
dispute_summary: str | None        # One-line dispute description
prior_broken_promises: int         # Count from history
promise_reliability: float | None  # Kept/made ratio (None = never promised)
evidence: list[str]                # Quoted lines supporting findings
promise_is_credible: bool          # Property: promise + reliability ≥ 0.5
```

**Rule-Based Logic** (deterministic, no external deps):
- **Promise detection**: Ordered regex patterns (strongest first: "will clear" 0.9 → "give us N days" 0.5)
- **Date extraction**: Explicit day ("21st"), weekday ("by Friday") — conservative, no "by month end"
- **Dispute detection**: Conservative patterns (explicit quality/supply/billing issues)
- **Credibility**: Uses `promise_reliability(customer_id)` from historical `PROMISE_HISTORY`
- **Most recent message wins** for promises; disputes block escalation/financing

---

### 2.2 Recovery Strategy Agent (FR-008)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Select Track A/B/C for one invoice with reasoning |
| **File** | `backend/app/agents/strategy.py` |
| **Interface** | `Strategist` (ABC) → `recommend(context: StrategyContext, as_of: date) → StrategyResult` |
| **Implementations** | `RuleBasedStrategist` (production), `LLMStrategist` (stub, OQ-02) |
| **Factory** | `get_strategist()` → returns rule-based while OQ-02 open |
| **Output Schema** | `StrategyRecommendation` (Pydantic, `schemas.py:88-109`) |

**Context Input** (`StrategyContext`):
```python
invoice_id, invoice_amount, due_date, invoice_date, acceptance_date
buyer_participates_in_treds: bool
probability_over_45: float           # From ML model
shortfall_projected: bool            # From forecast
contributes_to_shortfall: bool       # Material risk contributor
findings: InvestigatorFindings | None
```

**Recommendation Output**:
```python
action: "FOLLOW_UP" | "FINANCE" | "ESCALATE"
reason: str                          # Human-readable one-liner
deciding_factors: list[str]          # Specific inputs that drove choice
confidence: float                    # 0-1
```

**Rule-Based Decision Tree** (priority order):
1. **Dispute detected** → FOLLOW_UP (human must resolve first)
2. **Statutory flag (MSMED ≥45 days)**:
   - Promise but NOT credible → ESCALATE (pattern of broken promises)
   - No credible promise → ESCALATE
3. **TReDS eligible + shortfall projected** → FINANCE
4. **Credible promise** → FOLLOW_UP
5. **High delay risk (prob_over_45 ≥ 0.5)** → FOLLOW_UP
6. **Default** → FOLLOW_UP (routine)

**Tool Calls** (via `ToolBox` — every call recorded):
- `msmed_threshold()` → statutory flag + reason
- `statutory_interest()` → only if flag true (compound, 3× RBI rate)
- `treds_eligibility()` → eligible + reason (names ALL failing conditions)
- `financing_terms()` → mock discount terms (only if eligible + shortfall)

---

### 2.3 Execution Agent (Planned — FR-011, FR-012, FR-013)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Generate outreach drafts, mock TReDS submission payload, statutory escalation dossier |
| **Status** | Not implemented — Phase 4 work |
| **Current Handling** | Directly in `decision_engine/engine.py` + `outreach/` module (to be built) |
| **Requires** | Decision Engine approval gate (FR-010) before any output |

**Atomic Functions Needed**:
```python
# outreach/messages.py
generate_followup_draft(invoice, findings, promised_date) → str
generate_finance_draft(invoice, terms) → str
generate_escalation_draft(invoice, statutory_interest, msmed_details) → str

# outreach/treds.py
build_treds_payload(invoice, terms) → dict  # mock submission JSON

# outreach/dossier.py
build_escalation_dossier(invoice, msmed, interest, communications) → str  # PDF/HTML
```

---

## 3. Tool Boundary — The Agent/Determinism Contract (ADR-002, CON-05, NFR-003)

**File**: `backend/app/agents/tools.py`

### 3.1 ToolBox — Single Source of Truth for Statutory/Financial Values

```python
@dataclass
class ToolCall:
    tool: str                    # Function name
    arguments: dict              # JSON-serializable args
    result: dict                 # JSON-serializable result

@dataclass
class ToolBox:
    as_of: date
    calls: list[ToolCall] = field(default_factory=list)
    
    def msmed_threshold(acceptance_date, agreed_credit_days, ...) -> dict
    def statutory_interest(principal, acceptance_date, agreed_credit_days, rbi_bank_rate) -> dict
    def treds_eligibility(invoice_amount, due_date, invoice_is_buyer_approved, buyer_participates_in_treds, ...) -> dict
    def financing_terms(invoice_amount, due_date, annual_discount_rate) -> dict
    
    @property
    def trace(self) -> list[str]:  # Human-readable "tool(args) → result"
```

**Critical Rules**:
1. **Agents NEVER compute** statutory/financial values — only call `ToolBox` methods
2. **Every call recorded** as `ToolCall` → appears in audit trail as `decided_by="TOOL"`
3. **LLM implementations must use same tools** — `TOOL_SCHEMAS` defines OpenAI-style function signatures
4. **Fallback on failure** — if LLM refuses/malforms/times out, fall to rule-based (degraded > failed)

### 3.2 TOOL_SCHEMAS (Ready for LangGraph)

```python
TOOL_SCHEMAS = [
    {
        "name": "msmed_threshold",
        "description": "Check MSMED statutory threshold for an invoice",
        "parameters": {...}
    },
    {
        "name": "statutory_interest",
        "description": "Calculate statutory interest under MSMED Act",
        "parameters": {...}
    },
    {
        "name": "treds_eligibility",
        "description": "Check TReDS discounting eligibility",
        "parameters": {...}
    },
    {
        "name": "financing_terms",
        "description": "Simulate TReDS financing terms (mock)",
        "parameters": {...}
    }
]
```

---

## 4. Decision Engine — Orchestration Layer

**Files**: `backend/app/decision_engine/engine.py`, `service.py`

### 4.1 Core Flow (`service.py:build_action_queue()`)

```
_load_portfolio() → synthetic 30 invoices / ₹42.6L
    │
    ├── build_customer_stats() → per-customer delay stats
    ├── ML: extract_features() + DelayModel.predict() → prob_over_45 per invoice
    ├── build_forecast() → shortfall_projected + shortfall_ids (material risk)
    ├── build_threads() → CommunicationThread per invoice
    ├── Investigator.investigate() → InvestigatorFindings per invoice
    ├── Rules: check_msmed_threshold(), check_treds_eligibility()
    └── Strategist.recommend(StrategyContext) → StrategyResult + toolbox.trace
         │
         └── build_recommendation() → ActionRecommendation with full audit_trail
              │
              └── rank_queue() → ordered list (CRITICAL → HIGH → FOLLOW_UP, then value)
```

### 4.2 ActionRecommendation Structure

```python
invoice_id, customer_id, customer_name, invoice_amount, days_overdue
priority: CRITICAL | HIGH | FOLLOW_UP
recommended_action: FOLLOW_UP | FINANCE | ESCALATE
reason: str
approval_state: PENDING_APPROVAL | APPROVED | REJECTED
delay_probabilities: {bucket_0_15, bucket_16_30, bucket_31_45, bucket_over_45}
audit_trail: list[AuditEntry]  # ML, RULES, TOOL, AGENT, HUMAN
priority_score: float
```

### 4.3 Approval Gate (FR-010, CON-06)

```python
SENSITIVE_ACTIONS = {FINANCE, ESCALATE}

def approve(rec, actor) → rec with APPROVED + HUMAN audit entry
def reject(rec, actor) → rec with REJECTED + HUMAN audit entry (invoice state unchanged)
def assert_executable(rec) → raises ApprovalRequired if sensitive + not APPROVED
```

---

## 5. Data Structures — Communication & Promise Reliability

**File**: `backend/app/data/communications.py`

### 5.1 CommunicationThread

```python
Channel: WHATSAPP | EMAIL
Direction: OUTBOUND | INBOUND  # Only INBOUND used as evidence
Message: sent_on, channel, direction, body
CommunicationThread: invoice_id, customer_id, messages[]
    .inbound → list[Message]
    .last_inbound_date
    .outbound_count
```

### 5.2 Showcase Threads (5 Demo Cases)

| Invoice | Customer | Scenario | Key Evidence |
|---------|----------|----------|--------------|
| INV-1023 | ABC Logistics | Credible promise | "will clear by Friday 21st" + 80% reliability |
| INV-1038 | Global Retail | Financing candidate | No dispute, TReDS participant, shortfall projected |
| INV-1042 | Apex Trading | Broken promises | 3 prior promises, none kept → not credible |
| INV-1051 | Sunrise Textiles | Quality dispute | "shade variation" → blocks escalation/financing |
| INV-1047 | Nova Components | Routine | No signals → routine follow-up |

### 5.3 Promise History & Reliability

```python
PROMISE_HISTORY = {
    "CUST-001": {"promises_made": 5, "promises_kept": 4},  # 80% reliability
    "CUST-002": {"promises_made": 3, "promises_kept": 0},  # 0% → not credible
    ...
}

def promise_reliability(customer_id) → float | None
```

---

## 6. API Contracts — Agent Outputs to Frontend

**Backend**: `backend/app/api/schemas.py` (Pydantic, camelCase aliases)
**Frontend**: `frontend/src/lib/types.ts` (TypeScript mirror)

### 6.1 Key Response Types

```typescript
// Investigation screen (FR-003, FR-007, FR-014)
interface InvoiceInvestigation {
  invoice: Invoice;
  prediction: DelayPrediction;
  factors: PredictionFactor[];      // Top 3 features from XGBoost
  rules: RuleFlags;                 // statutoryFlag, statutoryInterest, tredsEligible
  findings: AgentFindings;          // paymentPromise, promisedDate, disputeDetected, confidence, evidence
  recommendedAction: RecommendedAction;
  reason: string;
  approvalState: ApprovalState;
  auditTrail: AuditEntry[];         // ML, RULES, TOOL, AGENT, HUMAN
}

// Action Queue item (FR-009)
interface ActionQueueItem {
  id: string;
  invoice: Invoice;
  priority: Priority;
  recommendedAction: RecommendedAction;
  reason: string;
  approvalState: ApprovalState;
  prediction: DelayPrediction;
}
```

---

## 7. LangGraph Integration — What's Needed for OQ-02

### 7.1 LLMInvestigator (Target Shape)

```python
class LLMInvestigator(Investigator):
    def __init__(self, fallback: Investigator = RuleBasedInvestigator()):
        self._fallback = fallback
        # LangGraph: single structured-output call
        # Prompt: thread rendered + promise_reliability as context
        # Output: InvestigatorFindings (validated)
        # On ANY failure: return self._fallback.investigate(thread, as_of)
```

### 7.2 LLMStrategist (Target Shape)

```python
class LLMStrategist(Strategist):
    def __init__(self, fallback: Strategist = RuleBasedStrategist()):
        self._fallback = fallback
        # LangGraph graph:
        #   - Agent node bound to TOOL_SCHEMAS
        #   - Loop until model stops requesting tools
        #   - Emit StrategyRecommendation (validated)
        # Rules:
        #   1. NEVER accept statutory/financial figure from model output
        #   2. Fall through to fallback on ANY failure
```

### 7.3 Integration Points

| Location | Change Needed |
|----------|---------------|
| `investigator.py:244` | `return LLMInvestigator()` when provider selected |
| `strategy.py:271` | `return LLMStrategist()` when provider selected |
| `backend/requirements.txt` | Add `langgraph`, `langchain-openai` (or chosen provider) |
| Environment | `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` |

---

## 8. Atomic Functionalities Checklist

### 8.1 Core Agent Functions (Already Implemented — Rule-Based)

- [x] **Investigator**: Regex promise detection with confidence scoring
- [x] **Investigator**: Date extraction (explicit day, weekday)
- [x] **Investigator**: Dispute detection (conservative patterns)
- [x] **Investigator**: Promise reliability from history
- [x] **Investigator**: Credibility assessment (`promise_is_credible`)
- [x] **Strategist**: MSMED threshold check via ToolBox
- [x] **Strategist**: Statutory interest calculation via ToolBox
- [x] **Strategist**: TReDS eligibility via ToolBox
- [x] **Strategist**: Financing terms simulation via ToolBox
- [x] **Strategist**: Decision tree (dispute → statutory → finance → promise → risk)
- [x] **Decision Engine**: Priority scoring (6-input blend)
- [x] **Decision Engine**: Tier assignment (CRITICAL/HIGH/FOLLOW_UP)
- [x] **Decision Engine**: Approval gate (PENDING_APPROVAL for FINANCE/ESCALATE)
- [x] **Decision Engine**: Audit trail construction (ML, RULES, TOOL, AGENT, HUMAN)
- [x] **Decision Engine**: Queue ranking (tier → value)

### 8.2 LLM Agent Integration (Blocked on OQ-02)

- [ ] **LLM Provider Selection** — Choose: OpenAI, Anthropic, Azure, local (Ollama), etc.
- [ ] **LangGraph Setup** — Add dependencies, configure graph compilation
- [ ] **LLMInvestigator Implementation** — Structured output call + fallback
- [ ] **LLMStrategist Implementation** — LangGraph graph with tool loop + fallback
- [ ] **Prompt Engineering** — Thread rendering, context injection, few-shot examples
- [ ] **Tool Calling Validation** — Ensure model only uses TOOL_SCHEMAS, no hallucinated values
- [ ] **Failure Handling** — Timeout, rate limit, refusal, malformed output → fallback
- [ ] **Observability** — Log LLM calls, token usage, latency, fallback rate

### 8.3 Execution Agent (Phase 4 — Not Started)

- [ ] **Outreach Draft Generation** — Follow-up, Finance, Escalation templates
- [ ] **Mock TReDS Payload Builder** — Submission JSON per spec
- [ ] **Statutory Dossier Builder** — PDF/HTML for MSME Samadhaan filing
- [ ] **Approval Integration** — `assert_executable()` before any generation
- [ ] **Audit Trail Extension** — HUMAN entries for approval, GENERATED for drafts

### 8.4 Persistence & Production Hardening

- [ ] **Postgres Persistence** — ActionRecommendation + audit_trail (FR-014)
- [ ] **Auth Hardening** — Replace `X-Org-Id` header with real auth (NFR-001)
- [ ] **Connector Credentials** — Secure storage for Tally/Zoho (NFR-002)
- [ ] **Latency Measurement** — p95 ≤ 3.0s @ 100 invoices (NFR-004)
- [ ] **Multi-org UI** — If OQ-03 resolves to full UI (currently schema-only)

---

## 9. Test Coverage — Agent Behavior Validation

| Test File | Validates |
|-----------|-----------|
| `test_investigator.py` | Promise detection with date, serial defaulter, hedged promises, acknowledgement ≠ promise, most recent wins, outbound ignored, dispute detection, silence handling, reliability history |
| `test_strategy.py` | Every statutory value via recorded tool call, interest only with breach, TReDS via tool, financing terms only when viable, trace names function+result, tool args serializable, TOOL_SCHEMAS complete, dispute blocks escalation, broken promise cited, credible promise → follow-up, financing wins when eligible+short, deciding_factors present, statutory interest in factors |
| `test_decision_engine.py` | Track selection logic, prioritization (statutory/shortfall → CRITICAL), ranking (tier → value), approval gate (PENDING→APPROVED/REJECTED, reject leaves state, audit records actor), audit trail names ML/RULES/AGENT, cites deterministic functions, promise credibility handling |

---

## 10. File Reference Map

```
backend/app/
├── agents/
│   ├── __init__.py              # Architecture docstring
│   ├── schemas.py               # InvestigatorFindings, StrategyRecommendation (Pydantic)
│   ├── investigator.py          # Investigator ABC, RuleBased, LLM stub, get_investigator()
│   ├── strategy.py              # Strategist ABC, RuleBased, LLM stub, get_strategist(), ToolBox
│   └── tools.py                 # ToolCall, ToolBox, TOOL_SCHEMAS (4 tools)
├── decision_engine/
│   ├── __init__.py              # Architecture docstring
│   ├── engine.py                # decide_action, score_priority, assign_priority, build_recommendation, rank_queue, approve/reject/assert_executable
│   └── service.py               # build_action_queue, get_cash_forecast, get_investigation, get_findings
├── rules_engine/
│   ├── msmed.py                 # check_msmed_threshold, calculate_interest, calculate_appointed_day
│   └── treds.py                 # check_treds_eligibility, simulate_financing
├── ml_core/
│   ├── model.py                 # DelayModel (XGBoost), predict(), top_factors
│   ├── forecast.py              # build_forecast (probabilistic 30-day)
│   └── features.py              # extract_features, build_customer_stats
├── data/
│   ├── communications.py        # CommunicationThread, showcase threads, PROMISE_HISTORY, promise_reliability
│   └── synthetic.py             # generate_dataset, sample_delay (multi-factor, no leakage)
├── canonical/
│   └── models.py                # CanonicalInvoice, CanonicalCustomer, CanonicalPayment, BusinessFinancialState
├── api/
│   ├── routes.py                # /action-queue, /summary, /forecast, /invoice/{id}
│   └── schemas.py               # API response models (camelCase, mirror frontend types.ts)
└── tests/
    ├── test_investigator.py
    ├── test_strategy.py
    └── test_decision_engine.py
```

---

## 11. Implementation Order for OQ-02 Resolution

1. **Choose LLM Provider** → Set `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` in env
2. **Add Dependencies** → `langgraph`, `langchain-{provider}`, `pydantic-ai` (optional for structured output)
3. **Implement LLMInvestigator** → Single structured call, thread→prompt, fallback on failure
4. **Implement LLMStrategist** → LangGraph graph with tool loop, emit StrategyRecommendation, fallback
5. **Wire Factories** → Change `get_investigator()` / `get_strategist()` to return LLM versions
6. **Run Agent Tests** → Ensure deterministic fallback still passes, LLM version produces valid schemas
7. **Measure Fallback Rate** → Target < 5% fallback in production traffic
8. **Load Test** → Verify NFR-004 (p95 ≤ 3.0s @ 100 invoices) with LLM calls

---

## 12. Key Constraints to Preserve

| Constraint | Code Location | Enforcement |
|------------|---------------|-------------|
| LLM never computes statutory/financial | `tools.py`, `strategy.py` | ToolBox only path; test validates every value via tool |
| Structured I/O only | `schemas.py` | Pydantic validation at factory boundary |
| Deterministic fallback stays | `investigator.py:16-18`, `strategy.py:12-16` | Not a placeholder — production fallback |
| Approval gate for sensitive actions | `engine.py:42-43`, `assert_executable()` | Exception raised if bypassed |
| Audit trail traces every figure | `engine.py:250-294`, `build_recommendation()` | ML/RULES/TOOL/AGENT/HUMAN entries |
| No label leakage in synthetic data | `synthetic.py:sample_delay()` | Multi-factor latent process; regression tests guard |

---

*Report generated from codebase analysis as of 2026-08-16. Source of truth: `docs/inception.md`, `docs/implementation-status.md`, and backend source files.*