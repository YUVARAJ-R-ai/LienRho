# LIENRHO — Capability Plan

**Source documents:** `docs/inception.md`, `docs/AGENTIC_ARCHITECTURE_REPORT.md`
**Tech stack (CON-01, hard):** Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic
**Inventories consulted:**
- `C:\ForbiddenKnowledge\atomic-capabilities\langgraph\langgraph-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\fastapi\fastapi-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\pydantic\pydantic-capabilities.md`
- `C:\ForbiddenKnowledge\atomic-capabilities\langchain\langchain-capabilities.md`

---

## Framework Capabilities (Inventory-Sourced)

*Read verbatim from ForbiddenKnowledge atomic-capability inventories. These are cross-cutting framework primitives — routing, validation, state management, tool calling, structured output — applicable to any Python/JS system.*

| Capability ID | Capability (exact text from inventory) | Framework |
|---|---|---|
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
| 1.4.1 | Retrieve the model's JSON schema (model_json_schema) | Pydantic |
| 1.4.2 | Retrieve the model's field metadata (model_fields) | Pydantic |
| 1.4.5 | Retrieve the core schema used for validation (model_core_schema via __pydantic_core_schema__) | Pydantic |
| 1.1.5 | Define abstract models as base classes | Pydantic |
| 2.11 | Add numeric constraints to a field (gt, ge, lt, le, multiple_of) | Pydantic |
| 2.12 | Add string constraints to a field (min_length, max_length, pattern) | Pydantic |
| 5.1 | Forbid extra fields not declared in the model (extra='forbid') | Pydantic |
| 5.4 | Make all fields immutable after construction (frozen=True) | Pydantic |
| 13.5 | Use Pydantic models in LangChain / LangGraph for structured output | Pydantic/LangGraph |
| 3.2 | Invoke a graph asynchronously | LangGraph |
| 3.3 | Run graphs in the background | LangGraph |
| 3.5 | Retry failed steps | LangGraph |
| 5.1 | Save checkpoints of graph state | LangGraph |
| 5.2 | Load a prior checkpoint | LangGraph |
| 6.1 | Maintain short-term working memory within a run | LangGraph |
| 7.1 | Pause execution for human review | LangGraph |
| 7.4 | Approve or reject proposed agent actions | LangGraph |
| 9.1 | Coordinate multiple agents within one workflow | LangGraph |
| 10.1 | Call external tools from within a node | LangGraph |
| 10.2 | Route to tool-calling nodes automatically | LangGraph |
| 10.3 | Integrate with multiple LLM providers | LangGraph |
| 11.1 | Store and retrieve the full message history of a conversation | LangChain |
| 11.2 | Trim conversation history to a token budget | LangChain |
| 13.1 | Force a chat model to return a Pydantic-validated structured object (with_structured_output) | LangChain |
| 13.2 | Force a chat model to return a TypedDict or JSON Schema | LangChain |
| 13.3 | Parse and validate nested structured output | LangChain |
| 13.4 | Inject format instructions into a prompt automatically | LangChain |
| 13.5 | Retry structured output generation on validation failure | LangChain |
| 15.1 | Evaluate graph outputs against datasets | LangGraph |
| 14.1 | Visualize graph structure | LangGraph |
| 14.2 | Trace execution paths | LangGraph |
| 14.3 | Capture state transitions | LangGraph |
| 14.4 | Collect runtime performance metrics | LangGraph |
| 14.5 | Detect issues in agent traces | LangGraph |
| 14.6 | Propose automated fixes for detected issues | LangGraph |
| 12.1 | Attach callback handlers to any Runnable for event-driven logging | LangChain |
| 12.2 | Receive events at run start, end, and error stages | LangChain |
| 12.3 | Stream token-level events via on_llm_new_token callback | LangChain |
| 12.5 | Collect run metadata (latency, model name, token counts) per step | LangChain |
| 1.1.1 | Define a model by subclassing BaseModel with type-annotated fields | Pydantic |
| 1.4.5 | Retrieve the core schema used for validation (model_core_schema via __pydantic_core_schema__) | Pydantic |
| 14.2 | Trace execution paths | LangGraph |

---

## Capability Map: FR-001 through FR-014 + NFR-001 through NFR-008

*Each requirement mapped to: Tech Stack (what from CON-01), Domain (custom LIENRHO component), and Gap/Coverage status (inventory-sourced or custom-built).*

### FR-001 — Ingest and normalize accounting data (TallyPrime connector)

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-001 | FastAPI routes (2.1-2.3, 3.3, 3.6), Pydantic schemas (5.1, 5.2, 6.1, 6.3, 6.5, 9.1, 9.2, 16.1, 1.1.1-1.1.5, 2.11-2.12, 5.1, 5.4, 13.5) | Tally connector module with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task`; canonical data normalization layer | **Inventory-sourced**: Framework primitives (FastAPI routing, Pydantic validation) enable the connector; domain logic (Tally XML/HTTP parsing) is custom-built |
| **Notes:** FastAPI provides route handlers, path/query param parsing, body/json validation, background task scheduling, and APIRouter splitting. Pydantic provides model definitions, field validation, constraints, and serialization. Connector implementation (TallyPrime HTTP/XML gateway) is custom per ASM-01/ CON-02. |

### FR-002 — Predict payment-delay probability per invoice

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-002 | XGBoost pipeline (not in inventory — custom ML stack per CON-01: scikit-learn / XGBoost) | XGBoost training pipeline with feature extraction; per NFR-005 quality gates (ROC-AUC ≥ 0.75, ECE ≤ 0.10) | **Custom build**: No ML model orchestration capability in any inventory. XGBoost model training and prediction scoring falls outside all inventoried frameworks. |
| **Notes:** Tech stack CON-01 specifies XGBoost/scikit-learn. Inventory covers framework plumbing but not model training pipelines. Custom component: feature extraction from canonical data, model training on synthetic dataset per ASM-02, NFR-005 quality gates before production use. |

### FR-003 — Explain each payment-delay prediction

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-003 | LangChain structured output (13.1, 13.2, 13.3, 13.4, 13.5), Pydantic schemas (1.1.1, 1.1.2, 1.2.1) | XGBoost top_factors output parsed into validated Pydantic schemas for frontend display | **Partial inventory**: LangChain structured output (IDs 13.1-13.5) can parse and validate XGBoost output into Pydantic schemas for frontend display. Feature importance extraction from XGBoost model is not covered by any inventory. |
| **Notes:** LangChain provides structured output forcing Pydantic-validated JSON from the LLM. Pydantic models (1.1.1-1.1.2, 1.2.1) validate the parsed output. XGBoost feature importance extraction is custom; LangChain acts as the parsing/validation layer between model and UI. |

### FR-004 — Forecast 30-day cash position

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-004 | FastAPI routes (2.1-2.2), LangGraph state (3.2, 3.3, 3.5, 5.1, 5.2, 6.1, 11.1, 14.1), Pydantic (5.1, 5.2) | Probabilistic 30-day cash-flow roll weighted by delay-model predictions; ADR-005 conservatism rules (conditioning on still-unpaid invoices, renormalizing buckets, >45 bucket never counts inside 30-day horizon) | **Partial inventory**: LangGraph state management (3.2-3.5, 5.1-5.2, 6.1, 11.1, 14.1) can persist forecast intermediate state and evaluate outputs against datasets. Probabilistic cash-flow forecasting weighted by delay-model predictions and ADR-005 conservatism rules are custom LIENRHO logic. |
| **Notes:** FastAPI provides the endpoint route. LangGraph provides state management, checkpointing, and dataset evaluation. ADR-005 conservatism rules (conditioning on still-unpaid invoices, renormalizing bucket mass, >45 bucket never entering 30-day horizon, no-prediction default-to-zero) are custom LIENRHO logic not in any inventory. |

### FR-015 — Identify invoices contributing to projected shortfall

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-015 | FastAPI routes (2.1), LangGraph evaluation (14.1) | Ranking invoices by marginal contribution to cash shortfall, per FR-004 forecast output | **Partial inventory**: FastAPI routing (2.1) can expose the attribution endpoint. LangGraph evaluation (14.1) can validate output against dataset expectations. Invoice contribution ranking by marginal contribution is custom LIENRHO logic. |
| **Notes:** FastAPI provides the route handler. LangGraph can validate outputs against dataset expectations. The actual ranking algorithm (by marginal contribution to shortfall) is LIENRHO-specific and not in any inventory. |

### FR-005 — Apply MSMED statutory threshold check

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-005 | FastAPI routes (3.3), Pydantic schemas (5.1, 5.2, 5.1 forbid extra), LangGraph HITL (7.1, 7.4) | Deterministic `check_msmed_threshold()` via ToolBox; per CON-05 deterministic functions must not be performed by LLM | **Partial inventory**: FastAPI provides request body parsing (3.3). Pydantic provides schema validation with `extra='forbid'` constraint. LangGraph provides human-in-the-loop pause/approve (7.1, 7.4). Deterministic `check_msmed_threshold()` function is custom per CON-05, NFR-003; not in any inventory. |
| **Notes:** FastAPI routing and body parsing enable the endpoint. Pydantic schemas with `extra='forbid'` enforce the no-extra-fields constraint. LangGraph human-in-the-loop enables the approval gate. The actual threshold computation (45-day MSMED statutory threshold from invoice acceptance date, not due date) is custom deterministic Python function. |

### FR-006 — Evaluate TReDS financing eligibility

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-006 | FastAPI routes (2.1, 2.3, 4.1), LangGraph tool nodes (10.1-10.3), Pydantic schemas (5.1, 5.2), LangChain structured output (13.1) | Deterministic `treds_eligibility()` via ToolBox; per CON-05 agents only call validated tool functions | **Partial inventory**: FastAPI provides routing and body parsing. LangGraph tool calling (10.1-10.3) enables tool node integration. LangChain structured output (13.1) ensures model output validates against tool schema. Deterministic `treds_eligibility()` function is custom per CON-05, NFR-003; not in any inventory. |
| **Notes:** FastAPI routing and body parsing enable the endpoint. LangGraph tool nodes (10.1-10.3) provide the framework for tool calls. The actual TReDS eligibility logic (invoice approved, buyer participates in TReDS, other conditions) is custom deterministic Python function per CON-05. |

### FR-007 — Investigate customer communications

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-007 | LangGraph nodes (10.1-10.3), LangChain history (11.1-11.2, 11.7), Pydantic schemas (1.1.1, 1.1.2, 1.2.1, 7.1-7.4, 15.1), FastAPI routes (2.1) | Investigator agent: regex promise detection, date extraction, dispute detection; ToolBox calls for MSMED/TReDS checks; LangChain conversation history as context | **Partial inventory**: LangGraph tool nodes (10.1-10.3) enable external tool calls. LangChain history (11.1-11.2, 11.7) provides conversation context. Pydantic schemas (1.1.1-1.1.2, 1.2.1, 7.1-7.4, 15.1) validate InvestigatorFindings. FastAPI route (2.1) exposes the investigation screen. Regex promise detection, date extraction, dispute detection (rule-based logic from AGENTIC_ARCHITECTURE_REPORT) are custom; framework provides the node structure and validation layer. |
| **Notes:** LangGraph provides the node framework. LangChain provides conversation history management. Pydantic validates the findings schema. The actual regex patterns, date extraction logic, and dispute detection rules are custom rule-based implementations per the AGENTIC_ARCHITECTURE_REPORT, with the framework providing the node/execution layer. |

### FR-008 — Recommend a recovery strategy per invoice

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-008 | LangGraph nodes (9.1-9.4, 10.1-10.3), LangChain history (11.1-11.2, 11.7), Pydantic schemas (1.1.1, 1.1.2, 1.2.1, 15.2, 15.5), FastAPI routes (2.1) | Strategist agent: rule-based decision tree (dispute → statutory → finance → promise → risk); ToolBox calls; LangChain history as context | **Partial inventory**: LangGraph coordinates multiple agents (9.1-9.4) and tool calls (10.1-10.3). LangChain history (11.1-11.2, 11.7) provides context. Pydantic validates StrategyRecommendation schema (1.1.1-1.1.2, 1.2.1, 15.2, 15.5). FastAPI route (2.1) exposes the recommendation. Rule-based decision tree (dispute → statutory → finance → promise → risk priority order) is custom per the AGENTIC_ARCHITECTURE_REPORT; framework provides the multi-agent coordination and validation layer. |
| **Notes:** LangGraph provides multi-agent coordination (9.1-9.4) and tool-call nodes (10.1-10.3). LangChain provides history context. Pydantic validates the output schema. The actual decision tree (dispute → statutory → finance → promise → risk in priority order) is custom per the AGENTIC_ARCHITECTURE_REPORT. |

### FR-009 — Prioritize actions into a daily action queue

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-009 | FastAPI routes (2.1-2.2, 2.7, 2.8, 2.9, 6.1, 6.3, 6.5, 15.1), LangGraph evaluation (14.1, 15.1) | Priority scoring (6-input blend: payment probability, cash urgency, invoice value, days overdue, legal urgency, financing availability); tier assignment (CRITICAL/HIGH/FOLLOW_UP) | **Partial inventory**: FastAPI provides routing (2.1-2.2, 2.7, 2.8, 2.9), dependency injection (6.1, 6.3, 6.5), and async path operations (15.1). LangGraph evaluation (14.1, 15.1) can validate queue ordering against dataset expectations. Priority scoring algorithm and tier assignment are custom LIENRHO logic. |
| **Notes:** FastAPI provides the route structure, dependency injection for scoring inputs, and async operation. LangGraph can validate queue ordering against dataset expectations. The actual priority scoring (6-input blend) and tier assignment (CRITICAL/HIGH/FOLLOW_UP with value ordering within tier) are custom LIENRHO logic. |

### FR-010 — Require human approval before executing sensitive actions

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-010 | LangGraph HITL (7.1-7.6), Pydantic schemas (5.1, 5.2), LangChain structured output (13.1) | Approval gate: recommendations written to PENDING_APPROVAL state; `assert_executable()` raises `ApprovalRequired` if sensitive + not APPROVED; explicit user action transitions to APPROVED/REJECTED | **Partial inventory**: LangGraph human-in-the-loop (7.1-7.6) provides the pause/approve/resume framework. Pydantic schemas (5.1, 5.2) validate agent I/O at factory boundary. LangChain structured output (13.1) ensures model output validates against Pydantic schema. The actual approval gate logic (PENDING_APPROVAL state, assert_executable exception, HUMAN audit entries) is custom per CON-06, FR-010; framework provides the HITL node structure. |
| **Notes:** LangGraph provides HITL nodes (7.1-7.6) for pause/inspect/modify/approve/interrupt/resume. Pydantic validates schemas at factory boundary. The actual approval gate implementation (state machine, assert_executable exception, audit trail entries) is custom per CON-06 and FR-010. |

### FR-011 — Generate draft outreach messages

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-011 | LangChain structured output (13.1-13.5), Pydantic schemas (1.1.1, 1.1.2, 1.2.1), FastAPI routes (2.1, 2.3, 4.1), LangGraph (7.1-7.6) | Draft message generation: prompt templates + LLM call for English formal email / WhatsApp-style message; per ASM-03/OQ-01: drafted-in-UI only for MVP | **Partial inventory**: LangChain structured output (13.1-13.5) forces Pydantic-validated JSON from LLM. Pydantic schemas (1.1.1-1.1.2, 1.2.1) validate the output. FastAPI routes (2.1, 2.3, 4.1) provide the endpoints. Prompt templates (3.1-3.9) render the messages. OQ-02 blocks LLM provider selection; rule-based draft templates are production fallback. Uncertainty: live WhatsApp Business API / SMTP integration not in scope for MVP (ASM-03/OQ-01). |
| **Notes:** LangChain structured output forces Pydantic-validated JSON. Pydantic validates schemas. FastAPI provides endpoints. Prompt templates render messages. OQ-02 is unresolved — rule-based templates cover MVP. Live API integration would be Phase 7+. |

### FR-012 — Generate a mock TReDS financing submission

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-012 | FastAPI routes (2.1, 2.3), Pydantic models (5.1, 5.2, 5.6, 4.12) | Mock TReDS submission payload (`invoice_id`, `amount`, `buyer`, `due_date`, `financing_required`, `estimated_proceeds`, `simulated_financing_cost`); per PRD §719–725: `estimated_proceeds = amount − simulated_financing_cost` | **Partial inventory**: FastAPI routing (2.1, 2.3) provides the endpoint. Pydantic models (5.1, 5.2, 5.6, 4.12) provide response serialization with alias support and unset/None field exclusion. `estimated_proceeds = amount − simulated_financing_cost` is deterministic calculation per CON-05, NFR-003; not in any inventory. |
| **Notes:** FastAPI provides the route handlers. Pydantic provides the response model with alias support and unset/None field exclusion. The actual payload fields and `estimated_proceeds = amount − simulated_financing_cost` calculation are custom per PRD §719–725 and CON-05. LangGraph not required — direct FastAPI endpoint. |

### FR-013 — Generate a statutory escalation dossier

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| FR-013 | FastAPI routes (2.1, 4.1), Pydantic models (5.1, 5.2, 4.12) | Dossier assembly (Udyam info, invoice, payment history, communication evidence, calculated statutory interest via deterministic `calculate_interest()`, proof of delivery, required documentation); per CON-08: manual filing only, no automated filing to MSME Samadhaan ODR | **Partial inventory**: FastAPI routing (2.1, 4.1) provides the endpoint. Pydantic models (5.1, 5.2, 4.12) provide response serialization with unset/None field exclusion. `calculate_interest()` deterministic function is custom per CON-08, NFR-003; not in any inventory. Manual filing (dossier only) per CON-08 is LIENRHO design choice. |
| **Notes:** FastAPI provides the route handlers. Pydantic provides the response model. The actual dossier content (Udyam info, invoice, payment history, communication evidence, statutory interest via deterministic function, proof of delivery) is custom per CON-08. Manual filing (dossier only, no automated filing to MSME Samadhaan ODR) per CON-08 is a LIENRHO design choice explicit in the PRD. |

### NFR-001 — Organization data isolation

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-001 | FastAPI dependency injection (6.1, 6.3, 6.5, 6.9), Pydantic schemas (5.1, 5.2, 5.1 forbid extra) | Row-level tenant scoping via `org_id` on every table; every query scoped by authenticated user's org at data-access layer; Pydantic model configuration (5.1, 5.4 frozen=True) forbids extra/unauthorized fields | **Inventory-sourced**: FastAPI dependency injection (6.1-6.9) scopes every query by the authenticated user's org_id. Pydantic model configuration (5.1, 5.4 frozen=True) forbids extra/unauthorized fields. This architectural pattern is enabled by FastAPI DI + Pydantic schemas — the pattern itself is inventory-sourced, though the specific `org_id` scoping implementation is LIENRHO's design choice. |
| **Notes:** FastAPI DI (6.1-6.9) provides the mechanism to scope queries by org. Pydantic (5.1, 5.4 frozen=True) forbids extra fields. The specific `org_id` on every table and data-access-layer scoping is LIENRHO's design choice, but the enabling pattern is from the inventory. |

### NFR-002 — Connector credential secrecy

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-002 | Pydantic SecretStr/SecretBytes (6.2.8) | Encrypted storage at rest, no plaintext secrets in logs; CI secret-scanning metric (target: 0 plaintext secrets) | **Partial inventory**: Pydantic 6.2.8 provides `SecretStr`/`SecretBytes` validation-only support — validates a secret string/bytes without exposing the value. Encryption at rest and log redaction are custom LIENRHO components; the inventory only provides validation primitives, not secret management. |
| **Notes:** Pydantic 6.2.8 provides `SecretStr`/`SecretBytes` validation. The actual encryption at rest, log redaction, and CI secret-scanning are custom LIENRHO components. The inventory only provides the validation primitive. |

### NFR-003 — Deterministic statutory/financial computation

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-003 | (no direct inventory coverage — ToolBox pattern is LIENRHO-specific) | Deterministic Python functions (`msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()`) with full audit tracing; every `ToolCall` recorded as `decided_by="TOOL"` in audit trail; Pydantic-validated tool input/output contracts | **No inventory coverage**: No direct inventory coverage for deterministic function computation. The ToolBox pattern (from AGENTIC_ARCHITECTURE_REPORT `backend/app/agents/tools.py`) provides the framework for tool nodes, but the actual function implementations are custom. |
| **Notes:** The inventory provides the framework (LangGraph tool nodes 10.1-10.3, Pydantic-validated schemas 5.1) for calling deterministic functions, but the actual function implementations (`msmed_threshold()`, `statutory_interest()`, `treds_eligibility()`, `financing_terms()`) are custom LIENRHO code. Every `ToolCall` is recorded in audit trail as `decided_by="TOOL"` (FR-014, 14.2-14.6). |

### NFR-004 — Action queue render latency

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-004 | FastAPI background tasks (9.1-9.4), async path operations (15.1) | p95 ≤ 3.0s @ 100 invoices target; custom load testing + optimization (query indexing, forecast caching, LangGraph checkpoint reuse) | **Partial inventory**: FastAPI background tasks (9.1-9.4) + async path operations (15.1) enable non-blocking queue construction. p95 ≤ 3.0s @ 100 invoices target is LIENRHO's perception threshold anchored to "keeps flow" (§16, §548). Custom load testing and optimization are LIENRHO-specific. |
| **Notes:** FastAPI background tasks and async operations enable non-blocking construction. The p95 ≤ 3.0s target and custom optimization (query indexing, forecast caching, LangGraph checkpoint reuse) are LIENRHO-specific, anchored to the "keeps flow" perception threshold. |

### NFR-005 — Payment-delay model quality

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-005 | (no direct inventory coverage — model quality gates are falsifiable targets) | ROC-AUC ≥ 0.75, ECE ≤ 0.10 on held-out split before model drives any recommendation; per-model-version reporting per PRD §91 (precision, recall, F1, bucket accuracy) | **No inventory coverage**: No direct inventory coverage for model quality gates. NFR-005 requires ROC-AUC ≥ 0.75 and ECE ≤ 0.10 on held-out split before model drives any recommendation. Per-model-version reporting per PRD §91. XGBoost training pipeline (FR-002) must pass these gates before production use. Custom component: model evaluation suite with held-out validation. |
| **Notes:** No inventory coverage. The quality gates themselves (ROC-AUC ≥ 0.75, ECE ≤ 0.10) are falsifiable targets, not framework primitives. Per-model-version reporting per PRD §91 is LIENRHO design. XGBoost pipeline must validate against these gates. |

### NFR-006 — Connector extensibility

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-006 | FastAPI module boundaries (16.1-16.5), Pydantic schemas (5.1, 5.1 forbid extra) | `AccountingConnector` interface (PRD §826–858) with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task`; zero changes to ML/rules/agent/decision-engine layers when new connector added | **Partial inventory**: FastAPI module boundaries (16.1-16.5) + Pydantic schemas (5.1, 5.1 forbid extra) enforce the interface contract. New connector implements interface; registration at single point requires 0 changes outside connector module. The `AccountingConnector` interface (PRD §826–858) and zero-change-extensibility pattern are LIENRHO design, enabled by the inventory's module-boundary and schema-forbid-extra primitives. |
| **Notes:** FastAPI module boundaries (16.1-16.5) organize the app into separate files. Pydantic schemas (5.1, 5.1 forbid extra) forbid extra/unauthorized fields. The `AccountingConnector` interface (PRD §826–858) with `get_invoices`, `get_customers`, `get_payments`, `get_expenses`, `create_task` and zero-change-extensibility pattern are LIENRHO design, but the enabling primitives (module boundaries, schema forbid-extra) are from the inventory. |

### NFR-007 — Decision traceability

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-007 | LangGraph trace (14.2-14.5), LangChain callbacks (12.1-12.5), Pydantic models (1.1.1, 1.4.5, 5.1, 5.2), ToolCall dataclass (from AGENTIC_ARCHITECTURE_REPORT) | Every action-queue item traceable via audit trail (FR-014) to specific ML prediction, rule evaluation, and agent output; `decided_by="TOOL"` for tool calls; "why" trail retrievable from invoice investigation screen | **Partial inventory**: LangGraph trace (14.2-14.5) captures execution paths and state transitions. LangChain callbacks (12.1-12.5) log LLM/tool calls with metadata. Pydantic models (1.1.1, 1.4.5, 5.1, 5.2) structure the "why" trail. ToolCall dataclass (from AGENTIC_ARCHITECTURE_REPORT) records every tool call as `decided_by="TOOL"`. The actual audit persistence + retrieval API is custom. |
| **Notes:** LangGraph trace captures execution paths. LangChain callbacks log LLM/tool calls. Pydantic models structure the trail. The actual audit persistence and retrieval API (queryable from invoice investigation screen) is custom LIENRHO code. |

### NFR-008 — Recommendation explainability

| Req | Tech Stack | Domain Component | Coverage |
|---|---|---|---|
| NFR-008 | FastAPI routes (2.1, 2.2), Pydantic schemas (5.1, 5.2), LangChain structured output (13.1-13.3) | First-time user sees recommended action + top reason on invoice investigation screen without additional explanation; ≥4/5 informal user-test reviewers correctness metric (assumed) | **Partial inventory**: FastAPI routes (2.1, 2.2) expose the recommendation. Pydantic schemas (5.1, 5.2) structure the response. LangChain structured output (13.1-13.3) ensures model output validates against Pydantic schema so top contributing factors are reliably surfaced. Uncertainty: informal user-test reviewer ≥4/5 correctness metric (NFR-008 target, assumed) not directly covered by any inventory — custom user-test harness required. |
| **Notes:** FastAPI routes expose the recommendation. Pydantic structures the response. LangChain structured output ensures model output validates against Pydantic schema so top contributing factors are reliably surfaced. The ≥4/5 user-test reviewer metric is LIENRHO's assumed user-goal, not directly covered by any inventory — custom user-test harness required. |

---

## Coverage Gaps (What the Inventory Doesn't Cover — Categorized)

| # | Requirement | Why the Inventory Doesn't Cover It | Category |
|---|---|---|---|
| 1 | FR-002: Predict payment-delay probability per invoice | No ML model orchestration inventory — XGBoost training is domain-specific per CON-01 stack | **Domain requirement** (expected custom; inventory covers framework plumbing only) |
| 2 | FR-004: Forecast 30-day cash position | No probabilistic cash-flow forecasting inventory — ADR-005 conservatism rules (conditioning on still-unpaid invoices, renormalizing buckets, >45 bucket behavior) are LIENRHO-specific | **Domain requirement** |
| 3 | FR-015: Identify invoices contributing to projected shortfall | No invoice-contribution attribution inventory — ranking by marginal contribution is FR-004 output–dependent | **Domain requirement** |
| 4 | FR-011: Generate draft outreach messages | No LLM prompt/template generation inventory — ASM-03/OQ-01 constraints (MVP: drafted-in-UI only, not live-sent) | **Domain requirement** |
| 5 | NFR-002: Connector credential secrecy | No secret management/crypto inventory — Pydantic 6.2.8 provides `SecretStr`/`SecretBytes` validation-only; encryption at rest, log redaction, CI secret-scanning are custom LIENRHO components | **Partial framework gap**: Inventory provides validation primitive (SecretStr/SecretBytes) but not secret management infrastructure (encryption at rest, log redaction, CI scanning) |
| 6 | NFR-005: Payment-delay model quality | No model quality/evaluation inventory — ROC-AUC ≥ 0.75, ECE ≤ 0.10 gates are falsifiable targets, not framework primitives; per-model-version reporting per PRD §91 | **Domain requirement** (quality gates are system-specific falsifiable targets) |
| 7 | NFR-008: Recommendation explainability | No informal user-test reviewer metric inventory — ≥4/5 correctness is LIENRHO user-goal (assumed); custom user-test harness required | **Domain requirement** (user-test harness is system-specific) |
| 8 | FR-012: Generate a mock TReDS financing submission | No mock TReDS payload builder inventory — payload fields + `estimated_proceeds = amount − simulated_financing_cost` deterministic calculation per PRD §719–725, CON-05 | **Partial framework gap**: Inventory provides FastAPI routing and Pydantic response models, but payload generation + deterministic calculation are LIENRHO-specific |
| 9 | FR-013: Generate a statutory escalation dossier | No document/dossier generation inventory — dossier content (Udyam info, invoice history, `calculate_interest()` deterministic function, proof of delivery, manual filing only per CON-08) | **Domain requirement** |
| 10 | NFR-003: Deterministic statutory/financial computation | No direct inventory coverage for deterministic function computation — ToolBox pattern provides framework (LangGraph tool nodes, Pydantic-validated contracts) but actual function implementations are custom | **Partial framework gap**: Inventory provides the calling framework (tool nodes, schema validation) but not the function implementations |
| 11 | NFR-004: Action queue render latency | No performance benchmarking inventory — p95 ≤ 3.0s @ 100 invoices is LIENRHO's perception threshold ("keeps flow" §16, §548); custom load testing required | **Partial framework gap**: Inventory provides FastAPI background tasks + async operations enabling non-blocking construction, but p95 target and optimization are LIENRHO-specific |
| 12 | FR-003: Explain each payment-delay prediction | No feature importance extraction inventory — LangChain structured output (13.1-13.5) can parse XGBoost output into Pydantic schemas, but feature importance extraction from XGBoost is custom | **Partial framework gap**: Inventory provides the parsing/validation layer (LangChain 13.1-13.5, Pydantic 1.1.1-1.1.2, 1.2.1) but not the feature importance extraction algorithm |

**Category legend:**
- **Domain requirement** = LIENRHO-specific business logic by design; expected to be custom-built; inventory provides enabling primitives only
- **Partial framework gap** = Inventory provides some relevant primitives but not the complete solution; LIENRHO builds on top of inventory capabilities
- **No inventory coverage** = Entirely absent from inventory; LIENRHO must build from scratch

---

## Implementation Order

1. **Set up FastAPI project with Pydantic models** — `app/main.py`, `app/schemas.py` (framework layer: FastAPI routing, Pydantic validation)
2. **Implement TallyPrime connector module** — `app/connectors/tally.py` (framework + domain boundary: FastAPI routes + Pydantic schemas + Tally custom parsing)
3. **Build canonical data layer & PostgreSQL schema** — `app/db/models.org_id` (framework: org_id scoping via FastAPI DI + Pydantic forbid-extra)
4. **Implement XGBoost delay model + feature extraction** — `app/ml/model.py` (domain: XGBoost pipeline per CON-01; NFR-005 quality gates)
5. **Build Rules Engine: MSMED threshold + TReDS eligibility + financing terms** — `app/rules/` (domain: deterministic Python functions per CON-05, NFR-003; ToolBox pattern)
6. **Implement LangGraph investigator agent (rule-based fallback)** — `app/agents/investigator.py` (framework on top of domain: LangGraph nodes + tool calls + Pydantic validation)
7. **Implement LangGraph strategist agent (rule-based fallback)** — `app/agents/strategy.py` (framework on top of domain: LangGraph multi-agent + decision tree + ToolBox calls)
8. **Build Decision Engine: priority scoring + approval gate + audit trail** — `app/decision_engine/engine.py` (framework + domain integration: FastAPI + LangGraph + Pydantic)
9. **Implement cash-flow forecast + shortfall invoice attribution** — `app/forecast.py` (domain: probabilistic 30-day roll per ADR-005; depends on step 4)
10. **Build outreach/message generation + mock TReDS + dossier generation** — `app/outreach/` (domain: depends on steps 5, 7, 9)
11. **Wire Next.js frontend: action queue, investigation screen, approval flow** — `frontend/` (framework consuming all above)
12. **Load testing: verify p95 ≤ 3.0s @ 100 invoices (NFR-004)** + model quality validation (NFR-005) (domain verification)

---
*Redesigned per user request: each FR/NFR mapped with Tech Stack (CON-01 layers), Domain Component (custom LIENRHO build), and Coverage status (inventory-sourced vs. custom-built). Coverage gaps explicitly categorized as Domain requirement or Partial framework gap. Source file column removed per previous user request; capability IDs and exact inventory text retained in Framework Capabilities section only.*