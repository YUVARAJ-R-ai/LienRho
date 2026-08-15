# Implementation status

Per-requirement state as of **2026-08-15**. Requirements are defined in [`inception.md`](inception.md); this file tracks what actually exists.

Legend: ✅ done · 🟡 partial · ⬜ not started

## Functional requirements

| ID | Requirement | State | Where | Notes |
|---|---|---|---|---|
| FR-001 | Ingest and normalize accounting data | 🟡 | `canonical/models.py`, `connectors/base.py` | Canonical model and `AccountingConnector` interface exist; no live Tally sync. `_load_portfolio()` reads the synthetic dataset and is the single swap point (#6) |
| FR-002 | Predict payment-delay probability | ✅ | `ml_core/model.py` | Four-bucket distribution, probabilities sum to 1.0 ± 0.01, no-history customers get neutral priors |
| FR-003 | Explain each prediction | ✅ | `ml_core/model.py`, `ml_core/features.py` | Top 3 factors in plain language. Uses gain importance, not per-prediction SHAP — see [`model-card.md`](model-card.md) |
| FR-004 | Forecast 30-day cash position | ✅ | `ml_core/forecast.py` | Probabilistic and conditioned on invoices still being unpaid (ADR-005) |
| FR-005 | MSMED statutory threshold check | ✅ | `rules_engine/msmed.py` | Deterministic. 44/45-day boundary tested. Counts from the §15 appointed day |
| FR-006 | TReDS eligibility | ✅ | `rules_engine/treds.py` | Deterministic, returns every failing condition rather than the first |
| FR-007 | Investigate customer communications | ✅ | `agents/investigator.py`, `data/communications.py` | Deterministic implementation runs today; `LLMInvestigator` is stubbed behind the same interface and unblocks on `OQ-02`. Findings include promise *credibility*, not just presence |
| FR-008 | Recommend a recovery strategy | 🟡 | `agents/strategy.py`, `agents/tools.py` | Track A/B/C selected over a recorded tool boundary; weighs promise credibility and disputes. Deterministic today — `LLMStrategist` swaps one class once `OQ-02` resolves (#13) |
| FR-009 | Prioritize into a daily action queue | ✅ | `decision_engine/engine.py`, `api/routes.py` | Tiered, ordered by descending value within tier |
| FR-010 | Human approval before sensitive actions | 🟡 | `decision_engine/engine.py`, `ApprovalPanel.tsx` | Gate enforced by `assert_executable()`; UI state is local-only and resets on restart |
| FR-011 | Generate draft outreach messages | ⬜ | — | #15 |
| FR-012 | Mock TReDS submission | 🟡 | `rules_engine/treds.py` | `simulate_financing()` computes the terms; the submission payload and UI are outstanding (#15) |
| FR-013 | Statutory escalation dossier | 🟡 | `rules_engine/msmed.py` | `calculate_interest()` produces the statutory figure the dossier needs; assembly is outstanding (#15) |
| FR-014 | Audit trail | 🟡 | `decision_engine/engine.py`, `AuditTrail.tsx` | Built and surfaced with ML/RULES/AGENT/HUMAN attribution; **in memory only**, resets on restart (#19) |
| FR-015 | Invoices contributing to a shortfall | ✅ | `ml_core/forecast.py` | Ranked by amount × probability-still-unpaid |

## Non-functional requirements

| ID | Requirement | State | Notes |
|---|---|---|---|
| NFR-001 | Organization data isolation | 🟡 | `org_scoped()` enforces it at the data-access layer, but `get_current_org_id()` trusts an unverified `X-Org-Id` header — **the requirement does not hold yet** (#20) |
| NFR-002 | Connector credential secrecy | ⬜ | No connector credentials exist yet |
| NFR-003 | Deterministic statutory computation | ✅ | All statutory/eligibility/interest values come from named functions in `rules_engine/`, reached only through `agents/tools.ToolBox`, which records every call. The audit trail shows each one as a `TOOL` entry with its arguments and result |
| NFR-004 | Action queue latency p95 ≤ 3.0s @ 100 invoices | ⬜ | **Not measured.** Needs a 100-invoice portfolio; the demo set is 30 |
| NFR-005 | Model quality | ✅ | ROC-AUC 0.834, ECE 0.031 — gate PASS. See [`model-card.md`](model-card.md) |
| NFR-006 | Connector extensibility | ✅ | Downstream modules depend only on canonical types; no connector-specific format leaks |
| NFR-007 | Decision traceability | 🟡 | Every queue item traces to its ML prediction and rule evaluation; not durable across restarts (#19) |
| NFR-008 | Recommendation explainability | 🟡 | Investigation screen leads with action + reason, then evidence. The ≥4/5 informal user test has not been run |

## Assumptions and open questions

| ID | State |
|---|---|
| ASM-01 | Untested — Tally gateway spike not attempted. Recommended cut for this build |
| ASM-02 | Holding — synthetic data in use; see ADR-004 for how leakage was avoided |
| ASM-03 | Holding — outreach will be drafted-in-UI |
| ASM-04 | **Unresolved** — no LLM provider chosen. No longer blocks FR-007: the rule-based investigator ships behind the same interface. Still blocks #13 |
| ASM-05 | Holding — `org_id` present on every table; no multi-org UI |
| OQ-01 | Defaulting to drafted-in-UI |
| OQ-02 | **Open.** No longer blocks FR-007 (deterministic fallback). Still blocks the LLM Strategy agent (#13) |
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
  → four Next.js screens reading the live API
```

Backend: 157 tests passing, ruff clean. Frontend: typechecks, lints, builds.

### The four showcase cases

| Invoice | Customer | Outcome | What it demonstrates |
|---|---|---|---|
| INV-1023 | ABC Logistics | FOLLOW_UP | A credible promise, with the date extracted from a WhatsApp thread |
| INV-1038 | Global Retail | FINANCE | TReDS-eligible and able to close the projected shortfall |
| INV-1042 | Apex Trading | ESCALATE | A promise the system *refuses to believe* — three prior promises, none kept |
| INV-1051 | Sunrise Textiles | FOLLOW_UP | The system declining to act: statutory threshold crossed, but a quality dispute must be resolved by a human first |
