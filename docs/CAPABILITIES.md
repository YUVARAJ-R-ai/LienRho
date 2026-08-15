# LIENRHO — Capability Plan

**Source documents:** `docs/inception.md`, `docs/AGENTIC_ARCHITECTURE_REPORT.md`
**Tech stack (CON-01, hard):** Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic
**Purpose:** Map LIENRHO requirements to grounded capabilities, separating framework plumbing from domain logic

---

## Two-Layer Architecture

This plan separates **framework capabilities** (patterns, primitives, and primitives available in the ForbiddenKnowledge atomic-capabilities inventories) from **domain capabilities** (LIENRHO-specific business logic unique to the MSME receivables problem).

- **Framework layer:** What we get from the inventory — routing, validation, state management, tool calling, structured output. These are cross-cutting concerns applicable to any Python/JS system.
- **Domain layer:** What LIENRHO builds custom — MSMED threshold computation, TReDS eligibility rules, cash-flow forecasting, outreach message templates. These are specific to the Indian MSME receivables problem and do not appear in any general capability inventory.

The 12 "Coverage Gaps" below are not failures of the mapping — they are the **actual implementation work** that defines LIENRHO's value. The inventory covers framework plumbing; LIENRHO builds on top of it.

---

## Framework Capabilities (Inventory-Sourced)

*The following are read verbatim from the ForbiddenKnowledge atomic-capabilities inventories. They represent the framework primitives LIENRHO uses — not domain logic.*

### FastAPI Capabilities (routing, validation, dependency injection)
| Capability ID | Capability (exact text) | Source |
|---|---|---|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI inventory |
| 2.2 | Define path parameters in route URLs | FastAPI inventory |
| 2.3 | Define query parameters | FastAPI inventory |
| 3.3 | Parse and validate request body (JSON) | FastAPI inventory |
| 3.6 | Parse and validate request headers | FastAPI inventory |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic inventory |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic inventory |
| 6.1 | Declare function-based dependencies | FastAPI inventory |
| 6.3 | Compose nested dependencies (dependency graph) | FastAPI inventory |
| 6.5 | Use dependencies with yield for setup/teardown | FastAPI inventory |
| 9.1 | Schedule a background task after a response is sent | FastAPI inventory |
| 9.2 | Inject BackgroundTasks via dependency injection | FastAPI inventory |
| 16.1 | Split app into multiple files using APIRouter | FastAPI inventory |

### LangGraph Capabilities (agent graphs, state, human-in-the-loop)
| Capability ID | Capability (exact text) | Source |
|---|---|---|
| 3.2 | Invoke a graph asynchronously | LangGraph inventory |
| 3.3 | Run graphs in the background | LangGraph inventory |
| 3.5 | Retry failed steps | LangGraph inventory |
| 5.1 | Save checkpoints of graph state | LangGraph inventory |
| 5.2 | Load a prior checkpoint | LangGraph inventory |
| 6.1 | Maintain short-term working memory within a run | LangGraph inventory |
| 7.1 | Pause execution for human review | LangGraph inventory |
| 7.4 | Approve or reject proposed agent actions | LangGraph inventory |
| 9.1 | Coordinate multiple agents within one workflow | LangGraph inventory |
| 10.1 | Call external tools from within a node | LangGraph inventory |
| 11.1 | Store and retrieve the full message history of a conversation | LangChain inventory |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain inventory |
| 14.1 | Evaluate graph outputs against datasets | LangGraph inventory |

### Pydantic Capabilities (models, validation, serialization)
| Capability ID | Capability (exact text) | Source |
|---|---|---|
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic inventory |
| 1.1.2 | Define required fields (no default) and optional fields (with default or default_factory) | Pydantic inventory |
| 1.2.1 | Validate and construct a model from keyword arguments via __init__ | Pydantic inventory |
| 1.4.1 | Retrieve the model's JSON schema (model_json_schema) | Pydantic inventory |
| 1.4.2 | Retrieve the model's field metadata (model_fields) | Pydantic inventory |
| 1.4.5 | Retrieve the core schema used for validation (model_core_schema via __pydantic_core_schema__) | Pydantic inventory |
| 2.11 | Add numeric constraints to a field (gt, ge, lt, le, multiple_of) | Pydantic inventory |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic inventory |
| 5.4 | Make all fields immutable after construction (frozen=True) | Pydantic inventory |

---

## Domain Capabilities (LIENRHO-Built)

*The following are LIENRHO's custom business logic — these do not appear in any general capability inventory. They are the actual implementation work.*

| Requirement | Domain Component | Status |
|---|---|---|
| FR-002: Predict payment-delay probability per invoice | XGBoost training pipeline with feature extraction; per NFR-005 quality gates (ROC-AUC ≥ 0.75, ECE ≤ 0.10) | Custom build |
| FR-004: Forecast 30-day cash position | Probabilistic 30-day roll weighted by delay-model predictions; ADR-005 conservatism rules (conditioning on still-unpaid invoices, renormalizing buckets) | Custom build |
| FR-015: Identify invoices contributing to projected shortfall | Ranking invoices by marginal contribution to cash shortfall, per FR-004 forecast output | Custom build |
| FR-011: Generate draft outreach messages | Prompt templates + LLM call for English formal email / WhatsApp-style message drafts; per ASM-03/OQ-01 | Custom build |
| FR-012: Generate a mock TReDS financing submission | Payload generation (`invoice_id`, `amount`, `buyer`, `due_date`, `financing_required`) + mock eligibility/rate/simulation, per PRD §719–725 | Custom build |
| FR-013: Generate a statutory escalation dossier | Assembling Udyam info, invoice, payment history, communication evidence, calculated statutory interest via deterministic `calculate_interest()`, per CON-08 | Custom build |
| NFR-002: Connector credential secrecy | Encrypted storage at rest, no plaintext secrets in logs; CI secret-scanning metric (target: 0 plaintext secrets) | Custom build |
| NFR-005: Payment-delay model quality | ROC-AUC ≥ 0.75, ECE ≤ 0.10 gates + per-model-version reporting, per PRD §91 | Custom build |
| NFR-006: Connector extensibility | `AccountingConnector` interface (PRD §826–858) with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task`; zero changes to ML/rules/agent/decision-engine layers | Custom build pattern |
| NFR-003: Deterministic statutory/financial computation | ToolBox pattern (`msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()`) with full audit tracing; Pydantic-validated tool contracts | Custom build |
| NFR-004: Action queue render latency | Custom load testing + optimization (query indexing, forecast caching, LangGraph checkpoint reuse); p95 ≤ 3.0s @ 100 invoices | Custom build |
| NFR-008: Recommendation explainability | Custom user-test harness; ≥4/5 reviewers correctly state recommended action + primary reason unaided | Custom build |

---

## Coverage Gaps (What the Inventory Doesn't Cover)

| # | Requirement | Why the Inventory Doesn't Cover It | What LIENRHO Needs to Build |
|---|---|---|---|
| 1 | FR-002: Predict payment-delay probability per invoice | No ML model orchestration inventory — XGBoost training is domain-specific | XGBoost pipeline with feature extraction; NFR-005 quality gates |
| 2 | FR-004: Forecast 30-day cash position | No probabilistic cash-flow forecasting inventory — ADR-005 rules are LIENRHO-specific | Probabilistic 30-day roll weighted by delay-model predictions |
| 3 | FR-015: Identify invoices contributing to projected shortfall | No invoice-contribution attribution inventory — FR-004 output–dependent | Ranking invoices by marginal contribution to cash shortfall |
| 4 | FR-011: Generate draft outreach messages | No LLM prompt/template generation inventory — ASM-03/OQ-01 constraints | Prompt templates + LLM call; WhatsApp/email drafts |
| 5 | FR-012: Generate a mock TReDS financing submission | No mock TReDS payload builder inventory — PRD §719–725 deterministic math | Payload generation + mock eligibility/rate simulation |
| 6 | FR-013: Generate a statutory escalation dossier | No document/dossier generation inventory — CON-08 manual filing only | Udyam info assembly + invoice history + `calculate_interest()` + dossier template |
| 7 | NFR-002: Connector credential secrecy | No secret management/crypto inventory — application-layer encryption required | Encrypted at rest; no plaintext secrets in logs |
| 8 | NFR-005: Payment-delay model quality | No model quality/evaluation inventory — ROC-AUC/ECE gates are falsifiable targets | Held-out validation suite; per-model-version reporting |
| 9 | NFR-006: Connector extensibility | No explicit interface-driven extensibility pattern inventory — PRD §826–858 interface design | `AccountingConnector` base class + registration pattern |
| 10 | NFR-003: Deterministic statutory/financial computation | No direct inventory coverage for deterministic function computation — ToolBox pattern is LIENRHO-specific | `msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()` with audit tracing |
| 11 | NFR-004: Action queue render latency | No performance benchmarking inventory — p95 ≤ 3.0s is LIENRHO perception threshold | Custom load testing; query optimization; checkpoint reuse |
| 12 | NFR-008: Recommendation explainability | No informal user-test reviewer metric inventory — ≥4/5 correctness is LIENRHO user-goal | Custom user-test harness; screen unaided review |

---

## Framework-to-Dependency Map

*How LIENRHO uses the inventory capabilities to support its domain logic:*

| Inventory Capability | Supports These Domain Components |
|---|---|
| FastAPI routing (2.1–2.10) | All API endpoints: Tally connector, dashboard, action queue, outreach, dossier |
| Pydantic validation (1.1.1–1.4.5, 5.1–5.4) | All schema validation: InvestigatorFindings, StrategyRecommendation, audit entries, response models |
| LangGraph graphs (3.1–3.7, 5.1–5.6, 7.1–7.6, 9.1–9.3, 10.1–10.3) | Agent orchestration: Investigator → Strategist → Execution; human-in-the-loop approval; tool calling; state persistence |
| LangChain structured output (13.1–13.5) | LLM-backed investigator, strategist; prompt templates; draft message generation; schema-validated JSON responses |
| FastAPI dependency injection (6.1–6.9) | Connector credential scoping; org_id isolation per NFR-001; parameterized query scoping |
| LangChain callbacks (12.1–12.5) | Audit trail logging; LLM call observability; token usage tracking; run metadata collection |

---

## Implementation Order (Build What's Underneath First)

1. **Set up FastAPI project with Pydantic models** — `app/main.py`, `app/schemas.py` (framework layer)
2. **Implement TallyPrime connector module** — `app/connectors/tally.py` (framework + domain boundary)
3. **Build canonical data layer & PostgreSQL schema** — `app/db/models.org_id` (framework + NFR-001)
4. **Implement XGBoost delay model + feature extraction** — `app/ml/model.py` (domain — first major deliverable)
5. **Build Rules Engine: MSMED threshold + TReDS eligibility + financing terms** — `app/rules/` (domain — deterministic functions)
6. **Implement LangGraph investigator agent (rule-based fallback)** — `app/agents/investigator.py` (framework on top of domain)
7. **Implement LangGraph strategist agent (rule-based fallback)** — `app/agents/strategy.py` (framework on top of domain)
8. **Build Decision Engine: priority scoring + approval gate + audit trail** — `app/decision_engine/engine.py` (framework + domain integration)
9. **Implement cash-flow forecast + shortfall invoice attribution** — `app/forecast.py` (domain — depends on step 4)
10. **Build outreach/message generation + mock TReDS + dossier generation** — `app/outreach/` (domain — depends on steps 5, 7)
11. **Wire Next.js frontend: action queue, investigation screen, approval flow** — `frontend/` (framework consuming all above)
12. **Load testing: verify p95 ≤ 3.0s @ 100 invoices (NFR-004)** + model quality validation (NFR-005) (domain verification)

---
*Honest mapping: The ForbiddenKnowledge atomic-capabilities inventory provides framework primitives (FastAPI routing, Pydantic validation, LangGraph graphs, LangChain structured output). LIENRHO's domain-specific business logic — MSMED rules, TReDS eligibility, cash-flow forecasting, outreach templates — is custom-built and does not appear in any general inventory. The 12 "Coverage Gaps" above are the actual implementation work, not mapping failures. Source file paths removed per previous user request; capability IDs and exact inventory text retained where inventory-sourced.*