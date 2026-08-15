# LIENRHO — Codebase Analysis Report

**Project:** LIENRHO — Working-Capital Decision Layer for Indian MSMEs (hackathon project, "ORIGINS 2026")
**Path analyzed:** `C:\DevLearning\LienRho`
**Analysis date:** 2026-08-15

---

## Table of Contents

1. [Architecture Style Identification](#1-architecture-style-identification)
2. [Key Modules and Their Responsibilities](#2-key-modules-and-their-responsibilities)
3. [Dependency Relationships](#3-dependency-relationships)
4. [Technology Stack Summary](#4-technology-stack-summary)
5. [Code Patterns and Conventions](#5-code-patterns-and-conventions)
6. [Entry Points and Data Flow](#6-entry-points-and-data-flow)
7. [External Integrations](#7-external-integrations)
8. [Testing Approach](#8-testing-approach)
9. [Build and Deployment Patterns](#9-build-and-deployment-patterns)
10. [Strengths and Areas for Improvement](#10-strengths-and-areas-for-improvement)

---

## 1. Architecture Style Identification

**Primary style: Modular monolith with strong hexagonal (Ports & Adapters) leanings and domain-driven discipline.**

The system is a single deployable FastAPI backend + single Next.js frontend + PostgreSQL, but the internal structure is far more deliberate than a typical layered CRUD app. Three architectural ideas are load-bearing:

1. **Layered core with strict one-way dependency direction.** The dependency graph is enforced by convention and verified by inspection: `api → decision_engine/service → {engine, agents, ml_core, rules_engine} → canonical`. Nothing points inward toward the domain except through sanctioned seams.

2. **Hexagonal ports-and-adapters, partially realized.** `connectors/base.py` defines `AccountingConnector` as an abstract port with no adapter yet. The canonical model (`canonical/models.py`) is the anti-corruption layer (ACL) — every connector must normalize into these shapes, and nothing downstream reads a connector's native format. `service.py`'s `_load_portfolio()` is explicitly documented as the swap point where a live Tally sync replaces the synthetic dataset.

3. **Agent tool-call boundary (ADR-002).** `agents/tools.py` is the *only* sanctioned way an agent obtains a statutory, financial, or eligibility value. Agents select strategy; they never compute. Every call is recorded into the audit trail. This is a deliberate, well-executed guard against LLM hallucination of legal/financial figures — the single most important architectural decision in the codebase.

The architecture is **not** microservices (correctly — small team, early-stage product, no independent scaling need), and it is **not** event-driven (fully synchronous, request-scoped, no message queues). The domain is rich enough to justify the DDD-style discipline (statutory rules, credibility judgments, approval state machines) but the implementation wisely avoids heavyweight DDD ceremony — no event sourcing, no sagas, no aggregates beyond simple dataclasses/Pydantic models.

**Trade-off named:** The layered purity costs some indirection (e.g., `build_recommendation()` in `engine.py` re-derives what the strategist already computed via `StrategyResult`), but the payoff is that the audit trail — the product's core trust mechanism — is structurally guaranteed rather than bolted on.

## 2. Key Modules and Their Responsibilities

### Backend (`backend/app/`)

| Module | Responsibility | Notable detail |
|---|---|---|
| `api/` | Delivery layer. `routes.py` (4 GET endpoints), `schemas.py` (camelCase response models via `serialization_alias`), `health.py` | Thin — no business logic; maps internal dataclasses to API schemas |
| `decision_engine/engine.py` | **The product's heart.** `decide_action()` (deterministic Track A/B/C: dispute > statutory breach > financing > credible promise > high delay risk > routine), `score_priority()` (weighted blend: 0.30·P(>45d) + 0.25·value + 0.20·overdue + 0.15·statutory + 0.10·shortfall), `assign_priority()`, `rank_queue()`, `build_recommendation()` (assembles the full ML→RULES→TOOL→AGENT audit trail), `approve()/reject()/assert_executable()` (human-in-the-loop gate) | `SENSITIVE_ACTIONS = {FINANCE, ESCALATE}`; `assert_executable()` is a function, not a convention, so the gate can't be silently forgotten |
| `decision_engine/service.py` | Orchestration seam. `build_action_queue()` loads portfolio → predictions → forecast → MSMED/TReDS checks → investigator + strategist → ranked queue. `get_cash_forecast()`, `get_investigation()`, `get_findings()` | `_load_portfolio()` is the Tally swap point; `_load_model()` uses `lru_cache` and degrades to rule-only mode when no artifact exists |
| `ml_core/model.py` | `DelayModel` wraps XGBClassifier; 4-bucket delay probabilities + top-3 explainable factors. `TrainingMetrics.meets_nfr_005()` gates ROC-AUC ≥ 0.75 and ECE ≤ 0.10. Custom `expected_calibration_error()` | Calibration is treated as first-class because the queue *ranks by probability* — a confidently wrong model silently reorders the queue |
| `ml_core/features.py` | 10 features (amount log, credit period, customer delay stats, relationship age, late rate, due-month seasonality, fiscal-year-end flag, amount vs customer median) | No-label-leakage discipline: no-history customers get neutral priors |
| `ml_core/forecast.py` | `build_forecast()` projects daily cash: current_cash + Σ(invoice × P(paid by day)) − expenses. `condition_on_still_unpaid()` renormalizes the delay distribution given an invoice is still unpaid. `rank_shortfall_contributors()` | Probabilistic conditioning is the key insight — a naive "everything arrives on due date" forecast would never surface the shortfall the product exists to warn about |
| `ml_core/train.py` | CLI training entry point | — |
| `rules_engine/msmed.py` | MSMED Act §15/§16: `check_msmed_threshold()` (inclusive 45-day boundary), `calculate_appointed_day()` (agreed credit period capped at 45 days), `calculate_interest()` (compound monthly rests at 3× RBI bank rate) | Pure stdlib, `Decimal` arithmetic, `ROUND_HALF_UP` to paise. Module docstring: "Nothing in this module may call an LLM" |
| `rules_engine/treds.py` | `check_treds_eligibility()` (returns every failing condition, min ₹50k, ≥5 days to due), `simulate_financing()` (mock discounting, CON-07) | — |
| `agents/investigator.py` | `Investigator` ABC → `RuleBasedInvestigator` (regex promise/dispute detection, promise credibility from history, conservative date extraction) + `LLMInvestigator` (stub, blocked on OQ-02) | Reads only *inbound* messages — "what we said to the customer is not evidence of their intent." Fallback is a genuine substitute, not a different code path |
| `agents/strategy.py` | `Strategist` ABC → `RuleBasedStrategist` + `LLMStrategist` (stub). Gathers facts *only* through `ToolBox`, then applies judgment | The trace shape is identical whether rule-based or LLM — which is why the trace is meaningful evidence |
| `agents/tools.py` | `ToolBox` — sanctioned boundary for statutory/financial values. Every call recorded as `ToolCall` → TOOL audit entry. `TOOL_SCHEMAS` OpenAI-style for future LangGraph | Thin wrappers over `rules_engine` — "exactly one implementation of each rule" |
| `agents/schemas.py` | Pydantic-validated `InvestigatorFindings`, `StrategyRecommendation` | Structured I/O is what makes the two agent implementations interchangeable |
| `canonical/models.py` | `CanonicalInvoice/Customer/Payment/BusinessFinancialState` — the ACL hub | `CanonicalPayment` denormalizes `customer_id` so ML features work even if invoices are archived |
| `connectors/base.py` | `AccountingConnector` ABC — port only, no adapter | — |
| `data/synthetic.py` | Seeded deterministic demo: 30 invoices ₹42.6L, 4 showcase cases (credible promise / financing / statutory escalation / dispute), multi-factor latent delay process | The 4 showcase cases map 1:1 to the 4 decision tracks — clearly designed to demo the decision logic |
| `data/communications.py` | Threads + `PROMISE_HISTORY` | — |
| `db/` | `session.py`, `models.py` (4 ORM tables, all `OrgScopedMixin.org_id`), `scoping.py` (`org_scoped()` as the only sanctioned query path) | Configured + migrated but **not used at runtime** — in-memory synthetic data is the de facto store |
| `outreach/` | Empty placeholder (FR-011/012/013) | — |
| `config.py` | pydantic-settings config | No `.env.example` files |

### Frontend (`frontend/src/`)

| Module | Responsibility |
|---|---|
| `app/` | App Router routes: `/` (action queue), `/invoice/[invoiceId]` (investigation), `/forecast`, `/approvals` |
| `lib/api.ts` | Server-side fetch client, `cache: "no-store"` — "a stale queue is worse than a slow one" |
| `lib/types.ts` | Hand-mirrored backend types (known drift risk, issue #21) |
| `lib/format.ts` | Indian currency formatting |
| `components/` | `AppShell`, `ActionQueueCard`, `ApprovalPanel`, `AuditTrail`, `ForecastChart`, `StatCard`, `Badge` (domain wrapper over shadcn/ui), plus `ui/` primitives |

## 3. Dependency Relationships

The dependency structure is the codebase's strongest architectural property. It is strictly layered and one-way:

```
api/routes.py
    └─→ decision_engine/service.py
            ├─→ decision_engine/engine.py
            ├─→ agents/{investigator, strategy, schemas}
            │       └─→ agents/tools.py
            │               └─→ rules_engine/{msmed, treds}   ← pure stdlib, dependency-free
            ├─→ ml_core/{features, forecast, model}
            │       └─→ canonical/models.py                    ← the hub
            └─→ data/{synthetic, communications}
                    └─→ canonical/models.py
```

Key properties:

- **`canonical/models.py` is the hub.** Every layer that touches business data reads canonical shapes. Nothing downstream reads connector-native formats.
- **`rules_engine` is dependency-free** (pure stdlib, `Decimal` arithmetic). This is deliberate and correct — statutory math must be reproducible and defensible, and it must never depend on an LLM.
- **`agents/tools.py` is the sanctioned value boundary.** Agents never compute statutory/financial values; they call tools that wrap `rules_engine`. The tool layer cannot quietly diverge from the rules because the arithmetic lives in exactly one place.
- **`db/` is currently orphaned** — `get_db` is never injected into routes. The ORM layer exists, is migrated, but is not on the runtime path. This is the single biggest structural inconsistency: the persistence layer is fully built but bypassed.
- **No circular imports observed.** The `from app.canonical.models import BusinessFinancialState` inside `service.get_cash_forecast()` is a local import but not a cycle — a minor style wart.
- **Frontend → backend is GET-only.** Server components call the REST API; the browser never talks to the backend directly. No POST/PUT endpoints exist yet (approvals are UI-only state).

## 4. Technology Stack Summary

### Backend
- **Language/runtime:** Python ≥ 3.12
- **Framework:** FastAPI ≥ 0.115, uvicorn
- **Validation/config:** Pydantic ≥ 2.9, pydantic-settings
- **Persistence:** SQLAlchemy ≥ 2.0, Alembic ≥ 1.13, psycopg[binary] ≥ 3.2, PostgreSQL 16-alpine (docker-compose)
- **ML:** xgboost ≥ 3.4.1, scikit-learn ≥ 1.9.0, numpy ≥ 2.5.2
- **Tooling:** uv + hatchling (build), pytest + httpx (test), ruff (lint, line-length 100)
- **Artifacts:** ML model + metrics as local JSON (`ml_core/artifacts/`)

### Frontend
- **Framework:** Next.js 16.3.1 App Router, React 19.2.8
- **Language:** TypeScript (strict), ESLint 9
- **Styling/UI:** Tailwind CSS v4, shadcn/ui (Base UI), class-variance-authority, tailwind-merge, tw-animate-css
- **Charts/icons:** recharts 3.x, lucide-react

### CI
- GitHub Actions: backend job (setup-uv, `uv sync`, `ruff check`, `pytest` — 118 tests), frontend job (Node 22, `npm ci`, `eslint`, `tsc --noEmit`, `next build`). **No deploy pipeline.**

## 5. Code Patterns and Conventions

1. **Abstract Base Class + Factory** — `Investigator`/`Strategist` ABCs with `get_investigator()`/`get_strategist()` factories returning the rule-based implementation while OQ-02 is open. Switching to LLM is a one-line change. The fallback is a *genuine substitute* (same tools, same trace shape, same validated output), not a degraded code path.
2. **Strategy Pattern with graceful degradation** — LLM implementations are stubs that raise `NotImplementedError`; the rule-based path ships. Documented rule: "A missing finding degrades a recommendation; an exception loses the whole action queue."
3. **Agent Tool-Call Boundary (ADR-002)** — `ToolBox` records every call (`ToolCall` dataclass with tool/arguments/result), producing the TOOL audit entries. `TOOL_SCHEMAS` are kept beside implementations so they can't drift, shaped for OpenAI-style structured tool calling / LangGraph.
4. **Human-in-the-Loop Approval Gate** — `ApprovalState` StrEnum (PENDING_APPROVAL → APPROVED/REJECTED), `SENSITIVE_ACTIONS` set, `assert_executable()` as an enforced function call before any execution. Rejection deliberately leaves invoice state untouched.
5. **Audit Trail / Event Ledger** — `AuditEntry(decided_by: ML|RULES|TOOL|AGENT|HUMAN, what, why)` built inside `build_recommendation()` — NFR-007 requires tracing an action without reading raw logs, so the trail is constructed at decision time, not bolted on.
6. **Enum-typed domain states** — `StrEnum` for `RecommendedAction`, `Priority`, `ApprovalState`, `PaymentStatus`. Frontend receives `.value` strings.
7. **Dataclass value objects** — `ActionRecommendation`, `AuditEntry`, `ForecastPoint`, `ShortfallContributor`, `CashForecast`, `StrategyContext`, `StrategyResult`, `ToolCall`. Pydantic only at the canonical/API boundaries.
8. **`Decimal` for all money** — statutory interest quantized to paise with `ROUND_HALF_UP`; forecast cash quantized to 0.01. No float money anywhere in the domain.
9. **Factory + Singleton** — `@lru_cache(maxsize=1)` on `_load_model()`; degrades to `None` (rule-only mode) on missing/corrupt artifact rather than failing the API.
10. **Deterministic rules engine** — pure functions, no I/O, no LLM, fully unit-testable. Boundary conditions are explicit and tested (44 days False, 45 days True).
11. **Probabilistic conditioning** — `condition_on_still_unpaid()` renormalizes the delay distribution; `probability_paid_by()` never counts the open-ended >45-day bucket as arrived inside a 30-day horizon ("assuming otherwise would quietly manufacture cash").
12. **Feature/label leakage discipline** — no-history customers get neutral priors; tests assert no-leakage invariants.
13. **Frontend conventions** — server components only, no client state library, `cache: "no-store"` fetches, domain `Badge` wrapper over shadcn/ui, camelCase API types hand-mirrored from backend.
14. **Documentation-in-code** — every module has a docstring explaining *why* (FR/BR/CON/NFR references, trade-offs, failure modes). This is unusually good for a hackathon codebase.

## 6. Entry Points and Data Flow

### Entry points
- **Backend:** `app/main.py` — FastAPI app, CORS for `localhost:3000`, mounts health + API routers.
- **ML training:** `ml_core/train.py` — CLI; produces `artifacts/delay_model.json` + `metrics.json`.
- **Frontend:** `src/app/layout.tsx` + `page.tsx`; routes `/`, `/invoice/[invoiceId]`, `/forecast`, `/approvals`.
- **DB:** Alembic migrations (2 revisions) via `migrations/`.

### Primary data flow (daily action queue)

```
GET /api/action-queue
  → service.build_action_queue()
      → _load_portfolio()          # synthetic dataset (Tally swap point)
      → _load_model()              # lru_cache'd DelayModel or None
      → build_customer_stats()     # per-customer delay statistics
      → extract_features() + model.predict()   # 4-bucket delay probs per invoice
      → get_cash_forecast()        # probabilistic 30-day projection
          → condition_on_still_unpaid() + probability_paid_by()
          → rank_shortfall_contributors()
      → shortfall_ids              # material contributors only (P ≥ 0.5)
      → build_threads() + investigator.investigate()   # promise/dispute findings
      → strategist.recommend()     # gathers facts via ToolBox (recorded)
      → build_recommendation()     # decide_action → score → priority → audit trail
      → rank_queue()               # tier first, then invoice value
  → api/routes.py maps to camelCase response schemas
  → Next.js server component fetches (no-store) → renders ActionQueueCard
```

### Secondary flows
- `GET /api/summary` — recomputes the queue + forecast for headline figures.
- `GET /api/forecast` — forecast points + top-5 shortfall contributors.
- `GET /api/invoice/{id}` — full investigation: prediction, top factors, MSMED/TReDS flags, statutory interest, agent findings, audit trail.
- `GET /health` — liveness.

**Notable:** every GET recomputes the entire pipeline from scratch (no caching beyond the model loader). For 30 invoices this is fine; it will not scale to a real portfolio without memoization or a persisted queue.

## 7. External Integrations

**Zero live external integrations.** This is the defining characteristic of the current state:

| Intended integration | Current state |
|---|---|
| TallyPrime/Zoho accounting | `AccountingConnector` ABC only — no adapter. `_load_portfolio()` is the documented swap point |
| LLM/LangGraph agents | `LLMInvestigator`/`LLMStrategist` stubs raising `NotImplementedError`; blocked on OQ-02. No langgraph/openai/anthropic in lockfile |
| TReDS financing | Mock `simulate_financing()` only (CON-07 explicitly marks it mock) |
| WhatsApp/email outreach | `outreach/` empty placeholder (FR-011/012/013) |
| PostgreSQL | Configured + migrated but **not used at runtime** — in-memory synthetic data |
| Fonts | Only external network dep: `next/font/google` (Geist) |

The system is fully self-contained and demo-runnable with zero external dependencies — a deliberate and correct hackathon strategy. The seams for every integration are clean and pre-designed.

## 8. Testing Approach

- **118 tests across 9 files** (`test_decision_engine`, `test_ml_core`, `test_forecast`, `test_msmed`, `test_treds`, `test_investigator`, `test_strategy`, `test_synthetic`, `test_health`).
- **Unit-test focused**, deterministic, no network/DB mocking needed (in-memory data).
- **Boundary-condition rigor** — e.g., MSMED inclusive 45-day boundary (44 False / 45 True), interest rounding to paise.
- **NFR gates as code** — `TrainingMetrics.meets_nfr_005()` (ROC-AUC ≥ 0.75, ECE ≤ 0.10) is an executable acceptance criterion, not a doc claim.
- **No-leakage invariants tested** — the ML feature discipline is enforced by tests.
- **Decision-logic tests** — Track A/B/C selection, priority bucketing, approval gate (`assert_executable` raising on unapproved sensitive actions), rejection leaving state untouched.
- **Gaps:** no integration tests against real Postgres; no frontend tests (no vitest/playwright); no contract tests between backend schemas and `types.ts` (the hand-mirroring is a known drift risk, issue #21); no test for the API layer itself beyond health.

## 9. Build and Deployment Patterns

- **Backend build:** uv + hatchling (`pyproject.toml`, wheel packages `app`). Dev deps in `[dependency-groups]`.
- **Frontend build:** `next build` (type-checked via `tsc --noEmit` in CI).
- **CI (GitHub Actions, `.github/workflows/ci.yml`):** two parallel jobs on push-to-main + PR — backend (setup-uv, `uv sync`, `ruff check .`, `pytest -q`) and frontend (Node 22, `npm ci`, `eslint`, `tsc --noEmit`, `next build`).
- **Local infra:** `docker-compose.yml` with Postgres 16-alpine; Alembic for schema.
- **No deploy pipeline** — no Dockerfile for the app itself, no hosting config, no environment management. CORS is hardcoded to `localhost:3000` with an explicit comment to tighten it before deployment.
- **Config:** pydantic-settings with defaults; **no `.env.example` files** — a real onboarding gap.

## 10. Strengths and Areas for Improvement

### Strengths

1. **Architectural discipline is exceptional for a hackathon.** One-way dependency direction, canonical ACL, dependency-free rules engine, sanctioned tool boundary — these are production-grade structural choices, and they're *documented with rationale* (ADR-002, NFR/FR/BR/CON references everywhere).
2. **The audit trail is structurally guaranteed, not bolted on.** Because every value flows through `ToolBox` and `build_recommendation()` constructs the trail at decision time, "the LLM didn't make the number up" is inspectable on screen. This is the product's trust mechanism and it's designed correctly.
3. **Human-in-the-loop is enforced, not suggested.** `assert_executable()` as a function, `SENSITIVE_ACTIONS` as a set, rejection leaving state untouched — the approval gate cannot be silently skipped.
4. **Probabilistic thinking is genuinely good.** The delay model predicts a 4-bucket distribution (not binary), the forecast conditions on still-unpaid invoices, and the open-ended bucket is never counted as arrived. The shortfall-contributor ranking (amount × P(still unpaid)) is the right metric.
5. **Graceful degradation everywhere.** Missing model artifact → rule-only mode; missing LLM → rule-based agents; corrupt artifact → `None` not crash. "A degraded recommendation is recoverable; a failed action queue is not."
6. **Domain correctness in the rules.** MSMED §15/§16 implemented with the agreed-credit-period cap, inclusive boundary, compound monthly rests at 3× RBI rate — and the caller supplies the rate rather than hardcoding it. The `decide_action()` docstring even explains the subtle financing insight (finance the *likely-to-pay* invoice, not the shortfall driver).
7. **No-label-leakage discipline** with neutral priors for no-history customers, enforced by tests.
8. **Clean frontend/backend split** — server components, no client state library, no-store fetches for a live queue.

### Areas for Improvement

1. **Persistence is built but bypassed — the biggest structural inconsistency.** SQLAlchemy models, org scoping, and Alembic migrations exist, but `get_db` is never injected into routes and everything runs on in-memory synthetic data. Audit trails and approvals reset on restart. Either wire the ORM in (FR-014) or remove the dead layer; the current state is the worst of both.
2. **Auth is stubbed and NFR-001 doesn't hold.** The `X-Org-Id` header is trusted unverified. Org scoping exists in the DB layer but is meaningless while the DB isn't used. This must be resolved before any real deployment.
3. **No deploy pipeline.** CI is solid; there is no way to ship. No app Dockerfile, no hosting, no env management, CORS hardcoded to localhost.
4. **`types.ts` hand-mirrors backend schemas** (issue #21) — guaranteed drift over time. Generate types from OpenAPI or add a contract test.
5. **Every GET recomputes the entire pipeline.** `build_action_queue()` is called repeatedly per request (and `get_investigation` calls it inside a loop over the queue). Fine for 30 invoices; will not survive a real portfolio. Needs memoization, a persisted daily queue, or a background job.
6. **No observability.** No logging framework, no structured logs, no metrics, no tracing. The audit trail is business observability, but there's no operational observability.
7. **No `.env.example` files** — onboarding friction and config drift risk.
8. **Frontend has no tests** — no component, integration, or e2e coverage; the approvals screen is UI-only state with no backend persistence.
9. **`_invoice_out()` in routes.py fabricates `invoice_date`/`due_date` as empty strings** for queue items — the queue path drops date data that the investigation path has. A schema inconsistency worth fixing.
10. **Local import inside `service.get_cash_forecast()`** (`from app.canonical.models import ...`) is a minor style wart; move to module top.
11. **`_explain()` uses global gain importance weighted by distance from training norm** — the code itself notes per-prediction SHAP would be better (issue #21). The `direction` field in the API is inferred heuristically (unsigned importance + elevated delay probability), which is honest but weak.
12. **LLM stubs raise `NotImplementedError`** rather than falling through to the rule-based fallback at runtime — the fallback wiring exists in the constructor (`self._fallback`) but the `recommend()`/`investigate()` methods don't use it yet. When OQ-02 resolves, the fallback path must be exercised, not just constructed.

### Verdict

LIENRHO is a remarkably well-architected hackathon project. The decision logic, the audit-trail design, the tool boundary, and the probabilistic forecast are genuinely production-quality thinking. The gaps are exactly what you'd expect from the demo stage: no live integrations, no real persistence, no auth, no deploy path. The seams for all of these are already designed and documented — the architecture will survive the team that built it, which is the highest compliment a codebase can earn.