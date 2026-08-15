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
uv run python -m app.ml_core.train          # trains the delay model (CUDA, CPU fallback)
uv run uvicorn app.main:app --reload        # :8000
./run-dev.sh start|stop|status              # or run it detached, capped to 12 cores

uv run pytest -q                            # 118 tests
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

- Auth is stubbed: `backend/app/db/scoping.py` trusts an unverified `X-Org-Id` header, so `NFR-001` does not actually hold yet (#20).
- The audit trail is in memory and resets on restart (#19).
- `frontend/src/lib/types.ts` mirrors backend response shapes by hand; nothing enforces it (#21).
- The action queue reads the synthetic portfolio. Swapping to a live sync means changing `_load_portfolio()` in `decision_engine/service.py` and nothing else (#6).

Full state: [`docs/implementation-status.md`](docs/implementation-status.md).

## Open questions that block design decisions

Check [`docs/inception.md`](docs/inception.md) §8 before building around `OQ-01`–`OQ-04` (outreach delivery, LLM provider, multi-org UI, baseline metric) — each has a stated default to build against until resolved.
