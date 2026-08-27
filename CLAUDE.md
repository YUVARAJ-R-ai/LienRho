# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

LIENRHO is a working-capital decision layer for Indian MSMEs: it reads receivables from an accounting system (TallyPrime primary, Zoho deferred) and produces one ranked, explainable daily action queue. Tally/Zoho stay the system of record — LIENRHO owns only *derived* data (predictions, forecasts, rule flags, agent findings, decisions, audit logs). It is not an accounting/bookkeeping app.

## Commands

Backend (`cd backend`, uses `uv`, Python 3.12+):

```bash
docker compose up -d                      # Postgres on :5432
uv sync
uv run alembic upgrade head
uv run python -m app.auth.seed            # demo org + login (idempotent)
uv run python -m app.ml_core.train        # trains delay model; CUDA with CPU fallback (--cpu forces CPU)
uv run uvicorn app.main:app --reload      # :8000
./run-dev.sh start|stop|status            # same, detached, nice'd; log at /tmp/lienrho-api.log
                                          # setsid/taskset are Linux-only and skipped elsewhere

uv run pytest -q                          # ~276 tests; no database needed
uv run pytest tests/test_msmed.py::test_name -q   # single test
uv run ruff check . --fix                 # line-length 100, migrations excluded
```

Frontend (`cd frontend`, needs the backend running — screens are server components that fetch from it):

```bash
npm install && npm run dev                # :3000
npx tsc --noEmit && npm run lint && npm run build
npm run generate:types                    # regenerate the API contract after a backend schema change
```

CI (`.github/workflows/ci.yml`) runs `ruff check` + `pytest` for backend and `lint` + `tsc --noEmit` + `build` for frontend. It does **not** train the model.

The model artifact is gitignored. Without it the API degrades to rule-only recommendations rather than failing, so everything still starts before you train. `train.py` exits non-zero if the NFR-005 gate (ROC-AUC ≥ 0.75, ECE ≤ 0.10) fails.

**macOS setup trap:** `xgboost` needs the OpenMP runtime, which is not a Python dependency and so `uv sync` will not supply it. Without it every import of `app.ml_core` fails and the entire suite errors at collection — including tests that have nothing to do with ML. Fix: `brew install libomp`.

## Non-negotiable rules

These come from ADRs/constraints in `docs/inception.md`; don't work around them without checking there first.

- **The LLM never computes a statutory, financial, or interest value** (`CON-05`, `ADR-002`). MSMED thresholds, TReDS eligibility, and interest are deterministic functions in `app/rules_engine/`. Agents reach them only through `app/agents/tools.py::ToolBox`, which records every call into the audit trail. Never hand an agent the rules functions directly.
- **Every agent output is a Pydantic-validated object** from `app/agents/schemas.py`. Free text never reaches the Decision Engine.
- **Sensitive actions require human approval** (`CON-06`, `FR-010`, `BR-APPROVAL`). FINANCE and ESCALATE are born `PENDING_APPROVAL`; rejecting must leave invoice state unchanged. Don't add a path that skips this, even for "obviously safe" cases.
- **Every table carries `org_id`**, scoped at the data-access layer via `app/db/scoping.py`, not per-endpoint (`NFR-001`, `BR-TENANT`).
- **Stack is fixed** (`CON-01`): Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic. Propose changes *within* it.
- **TReDS is mock-only** (`CON-07`) and the legal dossier is generated for manual filing, never auto-submitted (`CON-08`).

Requirements have permanent IDs (`FR-nnn`, `NFR-nnn`, `CON-nn`, `ADR-nnn`, `OQ-nn`, `STK-nn`, `ASM-nn`). Reference the ID rather than restating the requirement. If you add or change one, append to `docs/_id-registry.md` — IDs are never reused or renumbered; withdraw with a status note.

`docs/inception.md` is the source of truth; `prd.md` is the older narrative PRD and loses where the two disagree.

## Architecture

Modular monolith — one FastAPI deployable with module boundaries mirroring team roles (`ADR-001`), plus a separate Next.js app. A new connector, ML feature, agent, or screen should stay inside its own module (`NFR-006`).

Pipeline, and where each stage lives:

```
app/data/synthetic.py        portfolio (30 invoices) — the default source
app/connectors/tally/        TallyConnector over Tally's XML gateway (#6); ASM-01 unverified
app/ml_core/                 features.py → model.py (XGBoost, 4 delay buckets) → forecast.py (30-day cash)
app/rules_engine/            msmed.py, treds.py — deterministic, the only implementations of each rule
app/agents/                  investigator.py (reads comms), strategy.py (Track A/B/C), via tools.py
app/decision_engine/         engine.py (ranking + approval gate), service.py (assembles everything)
app/outreach/                drafts.py (FR-011), treds_submission.py (FR-012), dossier.py (FR-013)
app/api/routes.py            /api/action-queue, /summary, /forecast, /invoice/{id},
                             /invoice/{id}/draft, /invoice/{id}/artifact, /actions/{id}/approve|reject
frontend/src/app/            page.tsx (queue), invoice/[id], forecast, approvals
```

`decision_engine/service.py::build_action_queue` is the seam where all layers meet — read it first to understand the system. `_load_portfolio()` there is the single swap point for a live connector sync; nothing else changes. `settings.portfolio_source` selects `synthetic` (default) or `tally`.

Both agents ship as **two implementations behind one interface**: `RuleBasedInvestigator`/`RuleBasedStrategist` run today with no external dependency, `LLMInvestigator`/`LLMStrategist` are the production path unblocked when `OQ-02` (LLM provider) resolves. Both return the same validated object and make the same tool calls, so the Decision Engine can't tell them apart. The rule-based versions are the permanent fallback, not placeholders to delete. Selection logic is currently rule-based, not model-driven — say so accurately.

## Things that bite

- **Label leakage in synthetic data** (`ADR-004`). Delays come from a multi-factor latent process (`sample_delay`); any customer statistic used as a feature must be computed from *observed* payment history, never copied from a generating parameter. An earlier version handed the model its own constant and scored near-perfectly while learning nothing. Two tests in `tests/test_ml_core.py` guard this — extend them when adding a feature.
- **The forecast under-promises on purpose** (`ADR-005`). Treat any change that raises projected cash with suspicion.
- **Financing keys off whether a shortfall exists, not which invoice caused it** (`ADR-006`). The invoice driving a shortfall is usually the one no financier will discount.
- **MSMED overdue counts from the §15 appointed day**, not the invoice due date — callers must pass the actual `agreed_credit_days`, or every invoice silently gets the full 45 days. Boundary: 44 days = false, 45 = true.
- **Auth is real now** (#20): `app/db/scoping.py` derives `org_id` from a signed bearer token, not a header. `/api/*` requires one — the dependency sits on the router so a new endpoint cannot ship unauthenticated. Seed a login with `uv run python -m app.auth.seed` (`demo@lienrho.local` / `lienrho-demo`). The frontend keeps the token in an httpOnly cookie, so browser-side calls (approve/reject, draft) go through Next route handlers rather than straight to FastAPI.
- **Approvals and the audit trail are durable** (#19). The queue is derived on every request, so a decision stored on a recommendation object would vanish with it; decisions live in an `ApprovalStore` (`decision_engine/store.py`) and are replayed onto each rebuild. `settings.audit_store` picks `postgres` or the in-memory fallback. Asking for postgres is a preference, not a demand: an unreachable database degrades to memory and keeps serving rather than refusing to start. That degradation is **not silent** — it logs a warning and `/health` reports `auditStore.durable`, because a running API that drops every decision on restart is otherwise indistinguishable from a working one. The choice is made once per process and kept; retrying per call would strand decisions in memory that a later read against a recovered database would not see.
- **The Tally connector is unverified against a live instance** (`ASM-01`, #6). It is built to Tally's documented XML gateway format and tested against recorded fixtures in `tests/fixtures/tally/`, so envelope construction, failure handling, and canonical mapping are all covered — but no real TallyPrime has ever answered it. `parser.py` accepts several documented spellings per field for that reason. Two refusals matter: Tally answers a *rejected* request with HTTP 200 and `STATUS 0`, which must not read as an empty book, and an unparseable amount raises rather than becoming a zero that would silently clear a statutory breach.
- **The three artifacts gate themselves.** `assert_executable()` is called inside each generator rather than once upstream, so a new generator cannot quietly skip it. Drafts are deliberately ungated — a draft is what the user reads in order to decide.
- **`frontend/src/lib/types.ts` is derived, not written** (#21). It aliases onto `src/lib/api-types.ts`, generated from `backend/openapi.json` — regenerate both with `npm run generate:types` in `frontend/`, and commit the result; CI diffs them and fails if stale. The narrowed string unions carry `_DriftGuards` assertions, because `Omit<T, "k">` does not error when `k` is absent from `T` and a rename would otherwise slip through. Backend schemas use camelCase aliases (`response_model_by_alias=True`), and the schema carries the aliases.
- `frontend/CLAUDE.md` points at `frontend/AGENTS.md`, which `next dev` rewrites — Next.js 16 has breaking changes from training data; read `frontend/node_modules/next/dist/docs/` before writing frontend code.

## Docs

| File | Purpose |
|---|---|
| `docs/inception.md` | Source of truth: scope, constraints, FR/NFR catalog, ADRs, open questions |
| `docs/implementation-status.md` | Per-requirement: built vs. specified |
| `docs/model-card.md` | Model metrics, features, explainability, limitations |
| `docs/demo-checkpoints.md` / `docs/demo-script.md` | Phased plan; click path and narration |
| `docs/_id-registry.md` | Append-only ID ledger |
| `RESUME.md` | Start-of-session checklist and showcase invoices |
| `CONTRIBUTING.md` | Workflow, module ownership |

The `.claude/skills/lienrho-context` skill carries the domain glossary and business rules — consult it before proposing an architectural change or adding a dependency.

Four open questions have stated defaults in `docs/inception.md` §8 — build against those: `OQ-01` (outreach sent vs. drafted-only), `OQ-02` (LLM provider), `OQ-03` (multi-org UI), `OQ-04` (baseline triage time).
