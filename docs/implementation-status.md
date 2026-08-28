# Implementation status

Per-requirement state as of **2026-08-16**. Requirements are defined in [`inception.md`](inception.md); this file tracks what actually exists.

Legend: ✅ done · 🟡 partial · ⬜ not started

## Functional requirements

| ID | Requirement | State | Where | Notes |
|---|---|---|---|---|
| FR-001 | Ingest and normalize accounting data | 🟡 | `connectors/`, `sync/`, `canonical/models.py` | All three ACs met: `POST /api/sync` writes the canonical store, a failed sync records itself and leaves the prior portfolio intact, and re-runs are idempotent. Scheduled sync via `sync_interval_minutes`. `portfolio_source=database` serves the queue from the store. Still 🟡 only because **ASM-01 is unverified** — no live TallyPrime has answered the connector (#6) |
| FR-002 | Predict payment-delay probability | ✅ | `ml_core/model.py` | Four-bucket distribution, probabilities sum to 1.0 ± 0.01, no-history customers get neutral priors |
| FR-003 | Explain each prediction | ✅ | `ml_core/model.py`, `ml_core/features.py` | Top 3 factors in plain language. Uses gain importance, not per-prediction SHAP — see [`model-card.md`](model-card.md) |
| FR-004 | Forecast 30-day cash position | ✅ | `ml_core/forecast.py` | Probabilistic and conditioned on invoices still being unpaid (ADR-005) |
| FR-005 | MSMED statutory threshold check | ✅ | `rules_engine/msmed.py` | Deterministic. 44/45-day boundary tested. Counts from the §15 appointed day |
| FR-006 | TReDS eligibility | ✅ | `rules_engine/treds.py` | Deterministic, returns every failing condition rather than the first |
| FR-007 | Investigate customer communications | ✅ | `agents/investigator.py`, `data/communications.py` | Deterministic implementation runs today and is the fallback; `LLMInvestigator` (structured-output via `LiteLLMChatModel`) is implemented and swaps in when `llm_enabled` (#13). Findings include promise *credibility*, not just presence |
| FR-008 | Recommend a recovery strategy | ✅ | `agents/strategy.py`, `agents/tools.py` | Track A/B/C selected over a recorded tool boundary; weighs promise credibility and disputes. Deterministic today; `LLMStrategist` (LangGraph `create_agent` tool loop) is implemented behind the same interface and swaps in when `llm_enabled` (#13) |
| FR-009 | Prioritize into a daily action queue | ✅ | `decision_engine/engine.py`, `api/routes.py` | Tiered, ordered by descending value within tier |
| FR-010 | Human approval before sensitive actions | ✅ | `decision_engine/engine.py`, `decision_engine/store.py`, `ApprovalPanel.tsx` | Gate enforced by `assert_executable()` inside each generator. Decisions survive a queue rebuild *and* an API restart (#19) |
| FR-011 | Generate draft outreach messages | ✅ | `outreach/drafts.py` | Email and WhatsApp tones, referencing amount, due date, and the FR-007 evidence. Editable in the UI before send. Template implementation today; `LLMReminderDrafter` behind the same interface awaits `OQ-02` |
| FR-012 | Mock TReDS submission | ✅ | `outreach/treds_submission.py` | Payload matches prd.md §719–725; `estimated_proceeds = amount − financing_cost` enforced on the model, not just tested. Ineligible invoices are refused rather than submitted |
| FR-013 | Statutory escalation dossier | ✅ | `outreach/dossier.py` | All seven sections present. Interest comes through `ToolBox` so it lands in the audit trail as a recorded call. Missing evidence (proof of delivery) is stated as missing, never inferred |
| FR-014 | Audit trail | ✅ | `decision_engine/engine.py`, `decision_engine/store.py`, `AuditTrail.tsx` | ML/RULES/TOOL/AGENT/HUMAN attribution, persisted to `audit_log_entries` and ordered by a stored sequence rather than the timestamp. `actor` comes from the access token, not the request. An unreachable database degrades to in-memory rather than refusing to serve; `/health` reports `auditStore.durable` so the degraded state is observable (#19, #20) |
| FR-015 | Invoices contributing to a shortfall | ✅ | `ml_core/forecast.py` | Ranked by amount × probability-still-unpaid |

## Non-functional requirements

| ID      | Requirement                                    | State | Notes                                                                                                                                                                                                                                         |
| ------- | ---------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-001 | Organization data isolation                    | ✅    | `org_scoped()` enforces it at the data-access layer and `get_current_org_id()` now derives the org from a signed token. Auth sits on the `/api` router, so a new endpoint cannot ship unauthenticated. Acceptance test in `tests/test_auth.py` (#20)  |
| NFR-002 | Connector credential secrecy                   | 🟡     | Passwords are PBKDF2-HMAC-SHA256 (600k iterations, per-user salt) and the JWT signing key refuses to stay at its dev default outside development. Tally gateway credentials do not exist yet — the gateway is unauthenticated by design          |
| NFR-003 | Deterministic statutory computation            | ✅     | All statutory/eligibility/interest values come from named functions in `rules_engine/`, reached only through `agents/tools.ToolBox`, which records every call. The audit trail shows each one as a `TOOL` entry with its arguments and result |
| NFR-004 | Action queue latency p95 ≤ 3.0s @ 100 invoices | ✅     | **Measured 2026-08-28**: p50 153ms / p95 161ms / max 199ms over 30 runs against a 100-invoice portfolio (ML inference + rules + forecast + ranking). Gate PASS with ~18x margin. This is backend compute only — network and frontend render are additive but the margin easily absorbs them |
| NFR-005 | Model quality                                  | ✅     | ROC-AUC 0.834, ECE 0.044 — gate PASS. See [`model-card.md`](model-card.md)                                                                                                                                                                    |
| NFR-006 | Connector extensibility                        | ✅     | Acceptance criterion run for real: `SyntheticConnector` was added as a canned-data connector touching only `connectors/synthetic.py` and the registry in `connectors/__init__.py`. Downstream modules depend only on canonical types            |
| NFR-007 | Decision traceability                          | ✅     | Every queue item traces to its ML prediction and rule evaluation, and now survives a restart: approvals and the audit trail persist to Postgres (#19), verified by restarting the API mid-session and confirming the APPROVED state and HUMAN entry held |
| NFR-008 | Recommendation explainability                  | 🟡    | Investigation screen leads with action + reason, then evidence. The ≥4/5 informal user test has not been run                                                                                                                                  |

## Assumptions and open questions

| ID | State |
|---|---|
| ASM-01 | **Still untested.** `TallyConnector` is built to the documented XML gateway format and tested against recorded fixtures, but no live TallyPrime has answered it. The first run against a real instance *is* the spike (#6) |
| ASM-02 | Holding — synthetic data in use; see ADR-004 for how leakage was avoided |
| ASM-03 | Holding — outreach will be drafted-in-UI |
| ASM-04 | **Unresolved** — no LLM provider chosen. No longer blocks FR-007: the rule-based investigator ships behind the same interface. Still blocks #13 |
| ASM-05 | Holding — `org_id` present on every table; no multi-org UI |
| OQ-01 | Defaulting to drafted-in-UI |
| OQ-02 | **Open.** Both LLM agents (`LLMInvestigator`, `LLMStrategist`) are implemented and tested against `MockLLMClient`; OQ-02 is now only the deployment choice of provider/model/key, plus flipping `llm_enabled` |
| OQ-03 | Schema field only, no multi-org UI |
| OQ-04 | Open — no baseline measured |

## What runs today

```
synthetic portfolio (30 invoices, ₹42.6L) + communication threads
  → XGBoost delay predictions (4 buckets, explained)
  → Receivables Investigator: promises, disputes, promise credibility
  → Recovery Strategy agent selecting a track over a recorded tool boundary
  → deterministic MSMED + TReDS checks
  → probabilistic 30-day cash forecast + shortfall contributors
  → ranked action queue with approval gate and audit trail
  → human approval → generated artifact: reminder draft, mock TReDS
    submission, or MSMED dossier
  → four Next.js screens reading the live API
```

Backend: 326 tests passing, ruff clean. Frontend: typechecks, lints, builds.

**Note for anyone setting up on macOS:** `xgboost` needs the OpenMP runtime, which
is not a Python dependency. Without it every import of `app.ml_core` fails and
the whole suite errors at collection. Fix: `brew install libomp`.

### The four showcase cases

| Invoice | Customer | Outcome | What it demonstrates |
|---|---|---|---|
| INV-1023 | ABC Logistics | FOLLOW_UP | A credible promise, with the date extracted from a WhatsApp thread |
| INV-1038 | Global Retail | FINANCE | TReDS-eligible and able to close the projected shortfall |
| INV-1042 | Apex Trading | ESCALATE | A promise the system *refuses to believe* — three prior promises, none kept |
| INV-1051 | Sunrise Textiles | FOLLOW_UP | The system declining to act: statutory threshold crossed, but a quality dispute must be resolved by a human first |
