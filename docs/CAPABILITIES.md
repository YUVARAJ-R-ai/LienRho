# LIENRHO — Capability Plan

**Source documents:** `docs/inception.md`, `docs/AGENTIC_ARCHITECTURE_REPORT.md`
**Tech stack (CON-01, hard):** Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic
**Inventories consulted:**
- `C:\ForbiddenKnowledge\atomic-capabilities\langgraph\langgraph-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\fastapi\fastapi-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\pydantic\pydantic-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\langchain\langchain-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\pydantic-ai\pydantic-ai-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\celery\celery-capabilities.md`

---

## System Summary

LIENRHO is a decision-intelligence layer for Indian MSME owners that sits atop their existing accounting system (TallyPrime). It ingests receivables data, predicts payment delays via XGBoost, forecasts 30-day cash flow, applies deterministic MSMED/TReDS rule engines, and orchestrates LangGraph agents (Investigator for communication analysis, Strategist for recovery action selection) to produce a prioritized, explainable daily action queue with human-in-the-loop approval for sensitive actions. All statutory/financial computations are deterministic Python functions — LLMs only extract structured findings and select strategies via tool calls. The system owns only derived data (predictions, forecasts, rule-engine flags, agent findings, decisions, actions, audit logs); Tally/Zoho remain the system of record.

---

## Tech Stack Decision

The stack is **fixed per CON-01, hard**: Next.js/React (frontend), FastAPI/Python (backend), PostgreSQL (persistence), XGBoost/scikit-learn (ML), LangGraph (agent orchestration), Pydantic (validation/schemas). This was explicitly accepted in ADR-003 to preserve the CON-03 build window. The four inventories used are LangGraph (agent graphs, state management, human-in-the-loop, tool calling), FastAPI (routing, dependency injection, OpenAPI, background tasks, security), Pydantic (models, validation, serialization, JSON Schema, settings), and LangChain (structured output, tool schemas, LCEL composition, chat models, memory). No other inventories are needed; all stack layers are covered.

---

## Capability Map

### FR-001 — Ingest and normalize accounting data (TallyPrime connector)

**Frameworks involved:** FastAPI, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 2.2 | Define path parameters in route URLs | FastAPI |
| 2.3 | Define query parameters | FastAPI |
| 3.3 | Parse and validate request body (JSON) | FastAPI |
| 3.6 | Parse and validate request headers | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 6.1 | Declare function-based dependencies | FastAPI |
| 6.3 | Compose nested dependencies (dependency graph) | FastAPI |
| 6.5 | Use dependencies with yield for setup/teardown | FastAPI |
| 9.1 | Schedule a background task after a response is sent | FastAPI |
| 9.2 | Inject BackgroundTasks via dependency injection | FastAPI |
| 16.1 | Split app into multiple files using APIRouter | FastAPI |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| 1.1.2 | Define required fields (no default) and optional fields (with default or default_factory) | Pydantic |
| 1.2.1 | Validate and construct a model from keyword arguments via __init__ | Pydantic |
| 1.2.2 | Validate and construct a model from a dict or another model instance (model_validate) | Pydantic |
| 1.4.1 | Retrieve the model's JSON schema (model_json_schema) | Pydantic |
| 1.4.2 | Retrieve the model's field metadata (model_fields) | Pydantic |
| 1.4.5 | Retrieve the core schema used for validation (model_core_schema via __pydantic_core_schema__) | Pydantic |
| 1.1.5 | Define abstract models as base classes | Pydantic |
| 2.11 | Add numeric constraints to a field (gt, ge, lt, le, multiple_of) | Pydantic |
| 2.12 | Add string constraints to a field (min_length, max_length, pattern) | Pydantic |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic |
| 5.4 | Make all fields immutable after construction (frozen=True) | Pydantic |
| 13.5 | Use Pydantic models in LangChain / LangGraph for structured output | Pydantic/LangChain |

### FR-002 — Predict payment-delay probability per invoice

**Frameworks involved:** (XGBoost training pipeline — no direct inventory match; custom component)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| *No matching capability in any inventory* | — | — |
| **Notes:** XGBoost model training and prediction scoring falls outside all inventoried frameworks. Custom component: XGBoost training pipeline with feature extraction, per NFR-005 quality gates (ROC-AUC ≥ 0.75, ECE ≤ 0.10). |

### FR-003 — Explain each payment-delay prediction

**Frameworks involved:** (XGBoost feature importance — no direct inventory match; partial LangChain coverage)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| **Notes:** Feature importance extraction from XGBoost model is not covered by any inventory. LangChain structured output (IDs 13.1–13.5) can parse XGBoost top_factors output into validated Pydantic schemas for frontend display. |

### FR-004 — Forecast 30-day cash position

**Frameworks involved:** (Probabilistic cash-flow forecasting — no direct inventory match; LangGraph + LangChain partial)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 3.2 | Invoke a graph asynchronously | LangGraph |
| 3.3 | Run graphs in the background | LangGraph |
| 3.5 | Retry failed steps | LangGraph |
| 5.1 | Save checkpoints of graph state | LangGraph |
| 5.2 | Load a prior checkpoint | LangGraph |
| 6.1 | Maintain short-term working memory within a run | LangGraph |
| 11.1 | Pass runtime configuration into a graph run | LangGraph |
| 14.1 | Evaluate graph outputs against datasets | LangGraph |
| **Notes:** Probabilistic 30-day cash-flow forecasting weighted by delay-model predictions is not directly inventoried. LangGraph state management (IDs 2.1–2.5, 6.1–6.6) and checkpointing (5.1–5.6) can persist forecast intermediate state; LangChain LCEL (1.1–1.4) can stream incremental results. ADR-005 conservatism rules (conditioning on still-unpaid invoices, renormalizing buckets) require custom logic. |

### FR-015 — Identify invoices contributing to projected shortfall

**Frameworks involved:** (Cash-flow shortfall attribution — no direct inventory match; FastAPI + LangGraph partial)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 14.1 | Evaluate graph outputs against datasets | LangGraph |
| **Notes:** Ranking invoices by marginal contribution to cash shortfall is not directly inventoried. FastAPI routing (2.1–2.10) can expose the attribution endpoint; LangGraph evaluation (14.1) can validate output against demo-dataset expectations. Custom component: invoice contribution ranking per FR-004 forecast output. |

### FR-005 — Apply MSMED statutory threshold check

**Frameworks involved:** FastAPI, Pydantic, LangGraph (human-in-the-loop)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 7.1 | Pause execution for human review | LangGraph |
| 7.4 | Approve or reject proposed agent actions | LangGraph |
| 3.3 | Parse and validate request body (JSON) | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic |
| **Notes:** Deterministic `check_msmed_threshold()` call via ToolBox (from AGENTIC_ARCHITECTURE_REPORT) is the actual implementation — inventory coverage maps the surrounding framework capabilities that enable it (Pydantic schemas, LangGraph HITL pause/approve). The deterministic function itself is not in any inventory. |

### FR-006 — Evaluate TReDS financing eligibility

**Frameworks involved:** FastAPI, Pydantic, LangGraph (tool calling)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 10.1 | Call external tools from within a node | LangGraph |
| 10.2 | Route to tool-calling nodes automatically | LangGraph |
| 10.3 | Integrate with multiple LLM providers | LangGraph |
| 3.3 | Parse and validate request body (JSON) | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| **Notes:** `treds_eligibility()` ToolBox call (from AGENTIC_ARCHITECTURE_REPORT) is enabled by LangGraph tool calling (10.1–10.3) and Pydantic validation (5.1). LangChain structured output (13.1) ensures model output validates against the tool schema. |

### FR-007 — Investigate customer communications

**Frameworks involved:** LangGraph, LangChain, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 10.1 | Call external tools from within a node | LangGraph |
| 10.2 | Route to tool-calling nodes automatically | LangGraph |
| 11.1 | Store and retrieve the full message history of a conversation | LangChain |
| 11.2 | Trim conversation history to a token budget | LangChain |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| 1.1.2 | Define required fields (no default) and optional fields (with default or default_factory) | Pydantic |
| 1.2.1 | Validate and construct a model from keyword arguments via __init__ | Pydantic |
| 7.1 | Pause execution for human review | LangGraph |
| 7.2 | Inspect current agent state mid-run | LangGraph |
| 7.4 | Approve or reject proposed agent actions | LangGraph |
| 15.1 | Evaluate graph outputs against datasets | LangGraph |
| **Notes:** InvestigatorFindings Pydantic schema (from AGENTIC_ARCHITECTURE_REPORT) is validated via Pydantic (1.1.1–1.1.2, 1.2.1). Regex promise detection, date extraction, and dispute detection (rule-based logic from report) run as LangGraph nodes with tool calls for MSMED/TReDS checks (10.1–10.3). LangChain history (11.1–11.7) provides conversation context. Uncertainty: LLM-backed investigator (OQ-02) not yet implemented; rule-based fallback covers production. |

### FR-008 — Recommend a recovery strategy per invoice

**Frameworks involved:** LangGraph, LangChain, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 9.1 | Coordinate multiple agents within one workflow | LangGraph |
| 9.2 | Support hierarchical agent architectures | LangGraph |
| 9.3 | Support agent-to-agent handoff | LangGraph |
| 10.1 | Call external tools from within a node | LangGraph |
| 10.2 | Route to tool-calling nodes automatically | LangGraph |
| 10.3 | Integrate with multiple LLM providers | LangGraph |
| 11.1 | Store and retrieve the full message history of a conversation | LangChain |
| 11.2 | Trim conversation history to a token budget | LangChain |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| 13.5 | Retry structured output generation on validation failure | LangChain |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| 1.1.2 | Define required fields (no default) and optional fields (with default or default_factory) | Pydantic |
| 1.2.1 | Validate and construct a model from keyword arguments via __init__ | Pydantic |
| 15.2 | Evaluate intermediate reasoning steps | LangGraph |
| 15.5 | Backtest new agent versions against historical data | LangGraph |
| **Notes:** StrategyRecommendation Pydantic schema (from AGENTIC_ARCHITECTURE_REPORT) validated via Pydantic (1.1.1–1.1.2, 1.2.1). Rule-based decision tree (from report) runs as LangGraph nodes (9.1–9.4) with ToolBox calls (10.1–10.3). LangChain history (11.1–11.7) provides context. LLM strategist (LLMStrategist) stubbed behind identical interface per OQ-02. Deterministic fallback (RuleBasedStrategist) is production-ready. |

### FR-009 — Prioritize actions into a daily action queue

**Frameworks involved:** FastAPI, LangGraph, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 2.2 | Define path parameters in route URLs | FastAPI |
| 2.7 | Deprecate individual routes | FastAPI |
| 2.8 | Include multiple routers with prefix and tags | FastAPI |
| 2.9 | Assign operation IDs to routes | FastAPI |
| 6.1 | Declare function-based dependencies | FastAPI |
| 6.3 | Compose nested dependencies (dependency graph) | FastAPI |
| 6.5 | Use dependencies with yield for setup/teardown | FastAPI |
| 15.1 | Define async path operation functions | FastAPI |
| 14.1 | Evaluate graph outputs against datasets | LangGraph |
| **Notes:** Priority scoring (6-input blend: payment probability, cash urgency, invoice value, days overdue, legal urgency, financing availability) is computed in Decision Engine (from AGENTIC_ARCHITECTURE_REPORT) and exposed via FastAPI route. Tier assignment (CRITICAL/HIGH/FOLLOW_UP) maps to FastAPI response model. LangGraph evaluation (14.1, 15.1) can validate queue ordering against dataset expectations. |

### FR-010 — Require human approval before executing sensitive actions

**Frameworks involved:** LangGraph, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 7.1 | Pause execution for human review | LangGraph |
| 7.2 | Inspect current agent state mid-run | LangGraph |
| 7.3 | Modify agent state before resuming | LangGraph |
| 7.4 | Approve or reject proposed agent actions | LangGraph |
| 7.5 | Interrupt execution from within a node | LangGraph |
| 7.6 | Resume execution after human input | LangGraph |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| **Notes:** Approval gate (FR-010, CON-06) is implemented as LangGraph human-in-the-loop (7.1–7.6). Decision Engine writes recommendations in `PENDING_APPROVAL` state; only explicit user action transitions to `APPROVED`/`REJECTED`. `assert_executable()` raises `ApprovalRequired` if sensitive + not APPROVED. Pydantic schemas validate all agent I/O at factory boundary (13.1). |

### FR-011 — Generate draft outreach messages

**Frameworks involved:** LangChain, Pydantic, (LLM provider — OQ-02)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| 13.3 | Parse and validate nested structured output | LangChain |
| 13.4 | Inject format instructions into a prompt automatically | LangChain |
| 13.5 | Retry structured output generation on validation failure | LangChain |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| 1.1.2 | Define required fields (no default) and optional fields (with default or default_factory) | Pydantic |
| 1.2.1 | Validate and construct a model from keyword arguments via __init__ | Pydantic |
| 2.1.7 | Use structured output mode to force schema-validated JSON responses | LangChain |
| **Notes:** Draft message generation (FR-011) uses LangChain structured output (13.1–13.5) with Pydantic-validated schemas (1.1.1–1.1.2, 1.2.1). Prompt templates (3.1–3.9) render English formal email / WhatsApp-style message. OQ-02 blocks LLM provider selection; rule-based draft templates are production fallback per ASM-03. Uncertainty: live WhatsApp Business API / SMTP integration not in scope for MVP (ASM-03/OQ-01). |

### FR-012 — Generate a mock TReDS financing submission

**Frameworks involved:** FastAPI, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 2.3 | Define query parameters | FastAPI |
| 3.3 | Parse and validate request body (JSON) | FastAPI |
| 4.1 | Return a Pydantic model as a JSON response | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 5.6 | Serialize models using aliases by default (serialize_by_alias) | Pydantic |
| 4.12 | Exclude unset / None fields from response model | FastAPI |
| **Notes:** Mock TReDS submission payload (`invoice_id`, `amount`, `buyer`, `due_date`, `financing_required`, `estimated_proceeds`, `simulated_financing_cost`) generated via FastAPI route + Pydantic response model (4.1, 5.1). `estimated_proceeds = amount − simulated_financing_cost` per PRD §719–725 deterministic calculation (CON-05, NFR-003). LangGraph not required — direct FastAPI endpoint. |

### FR-013 — Generate a statutory escalation dossier

**Frameworks involved:** FastAPI, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 4.1 | Return a Pydantic model as a JSON response | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 4.12 | Exclude unset / None fields from response model | FastAPI |
| **Notes:** Dossier assembly (Udyam info, invoice, payment history, communication evidence, calculated statutory interest via deterministic `calculate_interest()`, proof of delivery, required documentation) is generated via FastAPI route + Pydantic response model. `calculate_interest()` function (from AGENTIC_ARCHITECTURE_REPORT, rules_engine/msmed.py) is deterministic — not in any inventory; framework coverage maps FastAPI routing (2.1) and Pydantic validation (5.1) that enable the endpoint. Manual filing to MSME Samadhaan ODR not integrated (CON-08, out of scope). |

### NFR-001 — Organization data isolation

**Frameworks involved:** FastAPI, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic |
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 2.7 | Deprecate individual routes | FastAPI |
| 2.8 | Include multiple routers with prefix and tags | FastAPI |
| 2.9 | Assign operation IDs to routes | FastAPI |
| 6.1 | Declare function-based dependencies | FastAPI |
| 6.5 | Use dependencies with yield for setup/teardown | FastAPI |
| 6.9 | Use parameterized (callable class) dependencies | FastAPI |
| **Notes:** Row-level tenant scoping via `org_id` on every table + authenticated user's org scoped at data-access layer. FastAPI dependency injection (6.1–6.9) scopes every query by the authenticated user's org_id. Pydantic model configuration (5.1, 5.4 frozen=True) forbids extra/unauthorized fields. Not a separate inventory capability — architectural pattern enabled by FastAPI DI + Pydantic schemas. |

### NFR-002 — Connector credential secrecy

**Frameworks involved:** (Secret management — no direct inventory match; Pydantic SecretStr partial)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 6.2.8 | Validate a secret string or bytes without exposing the value (SecretStr / SecretBytes) | Pydantic |
| **Notes:** Secret management (encrypted at rest, no plaintext secrets in logs) is not directly covered by any inventory. Pydantic SecretStr/SecretBytes (6.2.8) provides validation-only support — encryption at rest and log redaction require custom component. Connector credentials (Tally/Zoho API keys, OAuth tokens) stored encrypted via application-layer encryption; never appear in plaintext logs. CI secret-scanning metric (NFR-002 target: 0 plaintext secrets). |

### NFR-003 — Deterministic statutory/financial computation

**Frameworks involved:** (Tool-based deterministic computation — no direct inventory match; ToolBox pattern from report)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| **Notes:** No direct inventory coverage for deterministic function computation. The ToolBox pattern (from AGENTIC_ARCHITECTURE_REPORT `backend/app/agents/tools.py`) provides the `msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()` methods that agents call via LangGraph tool nodes (10.1–10.3). Every `ToolCall` is recorded in audit trail as `decided_by="TOOL"` (FR-014, 14.2–14.6). Pydantic-validated schemas (5.1) enforce tool input/output contracts. LangGraph rate-limiting (3.7) and retry (3.6) protect against transient failures. Custom component: deterministic Python functions (`calculate_interest()`, `check_msmed_threshold()`, `check_treds_eligibility()`) with full audit tracing. |

### NFR-004 — Action queue render latency

**Frameworks involved:** FastAPI, (performance — no direct inventory match)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| **Notes:** No direct inventory coverage for render latency. FastAPI background tasks (9.1–9.4) + async path operations (15.1) enable non-blocking queue construction. p95 ≤ 3.0s @ 100 invoices target requires custom load testing and optimization (query indexing, forecast caching, LangGraph checkpoint reuse). NFR-004 anchored to "keeps flow" perception threshold since this is the primary daily-use screen (inception.md §16, §548). |

### NFR-005 — Payment-delay model quality

**Frameworks involved:** (Model evaluation — no direct inventory match; NFR-005 metrics)

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| **Notes:** No direct inventory coverage for model quality gates. NFR-005 requires ROC-AUC ≥ 0.75 and ECE ≤ 0.10 on held-out split before model drives any recommendation. XGBoost model training pipeline (FR-002) must pass these gates before production use. Per-model-version reporting per PRD §91 (precision, recall, F1, bucket accuracy). Custom component: model evaluation suite with held-out validation, per NFR-005. |

### NFR-006 — Connector extensibility

**Frameworks involved:** FastAPI, Pydantic

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 16.1 | Split app into multiple files using APIRouter | FastAPI |
| 16.2 | Share dependencies across routers | FastAPI |
| 16.3 | Apply router-level prefixes and tags | FastAPI |
| 16.4 | Use sub-applications (Starlette mounting) | FastAPI |
| 16.5 | Organize models, routers, and dependencies in packages | FastAPI |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic |
| **Notes:** `AccountingConnector` interface (PRD §826–858) with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task` — zero changes to ML/rules/agent/decision-engine layers. FastAPI module boundaries (16.1–16.5) + Pydantic schemas (5.1, 5.1 forbid extra) enforce the interface contract. New connector implements interface; registration at single point requires 0 changes outside connector module. Custom component: `AccountingConnector` base class + registration pattern. |

### NFR-007 — Decision traceability

**Frameworks involved:** LangGraph, Pydantic, LangChain

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 14.2 | Trace execution paths | LangGraph |
| 14.3 | Capture state transitions | LangGraph |
| 14.4 | Collect runtime performance metrics | LangGraph |
| 14.5 | Detect issues in agent traces | LangGraph |
| 12.1 | Attach callback handlers to any Runnable for event-driven logging | LangChain |
| 12.2 | Receive events at run start, end, and error stages | LangChain |
| 12.3 | Stream token-level events via on_llm_new_token callback | LangChain |
| 12.5 | Collect run metadata (latency, model name, token counts) per step | LangChain |
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 1.4.5 | Retrieve the core schema used for validation (model_core_schema via __pydantic_core_schema__) | Pydantic |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| **Notes:** Every action-queue item traceable via audit trail (FR-014) to specific ML prediction, rule evaluation, and agent output. LangGraph trace (14.2–14.5) captures execution paths and state transitions. LangChain callbacks (12.1–12.5) log LLM/tool calls with metadata. Pydantic models (1.1.1, 1.4.5) structure the "why" trail retrievable from invoice investigation screen. `ToolCall` dataclass (from AGENTIC_ARCHITECTURE_REPORT) records every tool call as `decided_by="TOOL"`. Custom component: structured audit persistence + retrieval API. |

### NFR-008 — Recommendation explainability

**Frameworks involved:** FastAPI, Pydantic, LangChain

| Capability ID | Capability (exact text from inventory) | Framework |
|---------------|----------------------------------------|-----------|
| 5.1 | Define request/response schemas with Pydantic models | Pydantic |
| 5.2 | Validate string lengths, numeric ranges, regex patterns | Pydantic |
| 2.1 | Define route handlers for HTTP methods (GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD) | FastAPI |
| 2.2 | Define path parameters in route URLs | FastAPI |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| 13.3 | Parse and validate nested structured output | LangChain |
| **Notes:** First-time user sees recommended action + top reason on invoice investigation screen without additional explanation. FastAPI route (2.1–2.2) exposes the recommendation; Pydantic schema (5.1) structures the response. LangChain structured output (13.1–13.3) ensures model output validates against Pydantic schema, so top contributing factors are reliably surfaced. Uncertainty: informal user-test reviewer ≥4/5 correctness metric (NFR-008 target, assumed) not directly covered by any inventory — custom user-test harness required. |

---

## Coverage Gaps

| Requirement | Gap | Custom Component Needed |
|---|---|---|
| FR-002: Predict payment-delay probability per invoice | No direct ML model orchestration capability in any inventory | XGBoost training pipeline with feature extraction, per NFR-005 quality gates |
| FR-004: Forecast 30-day cash position | No probabilistic cash-flow forecasting capability | Probabilistic 30-day roll weighted by delay-model predictions, per ADR-005 conservatism rules |
| FR-015: Identify invoices contributing to projected shortfall | No invoice-contribution attribution capability | Ranking invoices by marginal contribution to cash shortfall, per FR-004 forecast output |
| FR-011: Generate draft outreach messages | No LLM prompt/template generation capability in inventory | Prompt templates + LLM call for English formal email / WhatsApp-style message drafts, per ASM-03/OQ-01 |
| FR-012: Generate a mock TReDS financing submission | No mock TReDS payload builder in inventory | Payload generation (`invoice_id`, `amount`, `buyer`, `due_date`, `financing_required`) + mock eligibility/rate/simulation, per PRD §719–725 |
| FR-013: Generate a statutory escalation dossier | No document/dossier generation capability | Assembling Udyam info, invoice, payment history, communication evidence, calculated statutory interest via deterministic `calculate_interest()`, per CON-08 |
| NFR-002: Connector credential secrecy | No secret management/crypto capability in inventory | Encrypted storage at rest, no plaintext secrets in logs, per NFR-002 metric |
| NFR-005: Payment-delay model quality | No model quality/evaluation capability | ROC-AUC ≥ 0.75, ECE ≤ 0.10 gates + per-model-version reporting, per NFR-005 |
| NFR-006: Connector extensibility | No explicit interface-driven extensibility pattern | `AccountingConnector` interface (PRD §826–858) with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task`; zero changes to ML/rules/agent layers |
| NFR-003: Deterministic statutory/financial computation | No direct inventory coverage for deterministic function computation | ToolBox pattern (`msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()`) with full audit tracing; Pydantic-validated tool contracts |
| NFR-004: Action queue render latency | No performance benchmarking capability in inventory | Custom load testing + optimization (query indexing, forecast caching, LangGraph checkpoint reuse); p95 ≤ 3.0s @ 100 invoices |
| NFR-008: Recommendation explainability | No informal user-test reviewer metric capability | Custom user-test harness; ≥4/5 reviewers correctly state recommended action + primary reason unaided |

---

## Implementation Order

1. **Set up FastAPI project with Pydantic models** (FR-001 scaffolding, NFR-001, NFR-002) — `app/main.py`, `app/schemas.py`
2. **Implement TallyPrime connector module** (FR-001 sync, FR-006 deterministic rules) — `app/connectors/tally.py`
3. **Build canonical data layer & PostgreSQL schema** (org_id isolation, NFR-001) — `app/db/models.py`
4. **Implement XGBoost delay model + feature extraction** (FR-002, NFR-005) — `app/ml/model.py`
5. **Build Rules Engine: MSMED threshold + TReDS eligibility + financing terms** (FR-005, FR-006, NFR-003) — `app/rules/`
6. **Implement LangGraph investigator agent (rule-based fallback)** (FR-007) — `app/agents/investigator.py`
7. **Implement LangGraph strategist agent (rule-based fallback)** (FR-008) — `app/agents/strategy.py`
8. **Build Decision Engine: priority scoring + approval gate + audit trail** (FR-009, FR-010, FR-014, NFR-007) — `app/decision_engine/engine.py`
9. **Implement cash-flow forecast + shortfall invoice attribution** (FR-004, FR-015, ADR-005) — `app/forecast.py`
10. **Build outreach/message generation + mock TReDS + dossier generation** (FR-011, FR-012, FR-013) — `app/outreach/`
11. **Wire Next.js frontend: action queue, investigation screen, approval flow** (FR-009, FR-010, FR-011) — `frontend/`
12. **Load testing: verify p95 ≤ 3.0s @ 100 invoices (NFR-004)** + model quality validation (NFR-005)

---
*Generated from architecture-mapper skill. All capability text copied verbatim from ForbiddenKnowledge atomic-capability inventories. Source file column removed per user request. Capability IDs, exact capability text, and Framework/tech stack columns retained in all tables.*