# Contributing to LIENRHO

## Source of truth

Before building anything, check [`docs/inception.md`](docs/inception.md) — it's the structured, current spec (stakeholders, scope, constraints, FR/NFR IDs, ADRs, open questions). `prd.md` is the original narrative PRD; where the two disagree, `inception.md` wins.

Every requirement/decision has a permanent ID (`FR-nnn`, `NFR-nnn`, `CON-nn`, `ADR-nnn`, `OQ-nn`, ...). Reference the ID in commits, PRs, and issues instead of restating the requirement. If you add or change one, append it to [`docs/_id-registry.md`](docs/_id-registry.md) — IDs are never reused or renumbered; withdraw with a status note instead of deleting.

## Non-negotiable rules

These come from the architecture ADRs and constraints — check with the team before working around them:

- **The LLM never computes a statutory, financial, or interest value** (`CON-05`, `ADR-002`). MSMED thresholds, TReDS eligibility, and interest are deterministic Python functions; agents call them as tool calls.
- **Every agent call is Pydantic-validated structured output.** Unvalidated/free-text output never reaches the Decision Engine.
- **Sensitive actions require explicit human approval** (`CON-06`, `FR-010`) — financing, escalation, and outreach sends all sit in `PENDING_APPROVAL` until a user approves or rejects.
- **Every table carries `org_id`**, scoped at the data-access layer (`NFR-001`, `BR-TENANT`).
- **Stack is fixed** (`CON-01`): Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic. Propose changes within it, not alternatives to it.
- **Synthetic training data must not leak the label** (`ADR-004`) — see below.
- **The cash forecast under-promises on purpose** (`ADR-005`). Treat any change that raises projected cash with suspicion.

## Module ownership

Adding a connector, an ML feature, an agent, or a screen should stay inside its module boundary (`NFR-006`) — a new connector shouldn't require touching ML, rules, or the decision engine.

| Role | Module(s) |
|---|---|
| ML | ML Core (payment-delay model, cash forecast) |
| Backend / connectors | Connectors, canonical data layer, rules engine, outreach/document generation |
| Agents / LLM orchestration | LangGraph agents, Pydantic schemas, tool-call boundary |
| Frontend | Dashboard, action queue, investigation, forecast, approval screens |

## Running things

```bash
# Backend
cd backend
docker compose up -d                        # Postgres on :5432
uv sync
uv run alembic upgrade head
uv run python -m app.auth.seed              # demo org + login (every /api route needs a token)
uv run python -m app.ml_core.train          # trains the delay model (CUDA, CPU fallback)
uv run uvicorn app.main:app --reload        # :8000
./run-dev.sh start|stop|status              # or run it detached, capped to 12 cores

uv run pytest -q                            # 326 tests; no database needed
uv run ruff check . --fix

# Frontend (needs the backend running)
cd frontend
npm install && npm run dev                  # :3000
npx tsc --noEmit && npm run lint
```

Training exits non-zero if the NFR-005 quality gate fails. The API degrades to rule-only recommendations when no model artifact exists, so it still starts before you train.

## Adding a feature to the ML model

Check it for label leakage first (`ADR-004`). A feature must be computable *before* the invoice is paid, and any customer statistic must come from observed payment history rather than a generating parameter. `tests/test_ml_core.py` has two guards for this — extend them rather than assuming.

## Workflow

1. Pick up or open an issue against the relevant `FR`/`NFR` ID.
2. Branch off `main`.
3. Open a PR referencing the issue/requirement ID; link any `ASM`/`OQ` items your change resolves or depends on.
4. If your change touches an `FR`, `NFR`, `CON`, or `ADR`, update `docs/inception.md` and `docs/_id-registry.md` in the same PR.

## Known gaps worth knowing before you build on them

- **Adding an npm dependency from macOS breaks `npm ci` on Linux.** `npm install` on darwin prunes optional dependencies that only resolve on Linux (`@emnapi/core`, `@emnapi/runtime`, reached through the wasm fallback for the Tailwind/lightningcss native binary). The lockfile it writes then fails `npm ci` in CI with "Missing: … from lock file", while every local check passes because `node_modules` is already populated. `--os=linux --cpu=x64` does not fix it on npm 11. If you add a frontend dependency, verify with `npm ci` in a clean copy of just `package.json` + `package-lock.json` before pushing. This is why the OpenAPI type generator is pinned as `npx -y openapi-typescript@7.13.0` in the `generate:types` script rather than being a devDependency — it runs twice, so it does not need to be in the dependency tree, and keeping it out leaves the lockfile untouched.
- On macOS, `xgboost` needs `brew install libomp` — it is not a Python dependency, and without it the whole test suite errors at collection.
- `uv run pytest` needs no database, but `test_sync.py` and the Postgres half of `test_approval_store.py` **skip** without one. A green local run is not proof those paths work; CI runs them against a real Postgres.
- `frontend/src/lib/types.ts` is generated from `backend/openapi.json`. After changing a response model, run `npm run generate:types` in `frontend/` and commit the result — CI diffs it and fails if stale (#21).
- The Tally connector is written to the documented XML gateway but has never run against a live instance (`ASM-01`, #6). Its parser accepts several documented spellings per field for exactly that reason.
- The agents run deterministically. `llm_enabled` is off pending `OQ-02`; the LLM implementations exist and fall back to the rule-based ones on any failure (#13).

Full state: [`docs/implementation-status.md`](docs/implementation-status.md).

## Open questions that block design decisions

Check [`docs/inception.md`](docs/inception.md) §8 before building around `OQ-01`–`OQ-04` (outreach delivery, LLM provider, multi-org UI, baseline metric) — each has a stated default to build against until resolved.
