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

## Module ownership

Adding a connector, an ML feature, an agent, or a screen should stay inside its module boundary (`NFR-006`) — a new connector shouldn't require touching ML, rules, or the decision engine.

| Role | Module(s) |
|---|---|
| ML | ML Core (payment-delay model, cash forecast) |
| Backend / connectors | Connectors, canonical data layer, rules engine, outreach/document generation |
| Agents / LLM orchestration | LangGraph agents, Pydantic schemas, tool-call boundary |
| Frontend | Dashboard, action queue, investigation, forecast, approval screens |

## Workflow

1. Pick up or open an issue against the relevant `FR`/`NFR` ID.
2. Branch off `main`.
3. Open a PR referencing the issue/requirement ID; link any `ASM`/`OQ` items your change resolves or depends on.
4. If your change touches an `FR`, `NFR`, `CON`, or `ADR`, update `docs/inception.md` and `docs/_id-registry.md` in the same PR.

## Open questions that block design decisions

Check [`docs/inception.md`](docs/inception.md) §8 before building around `OQ-01`–`OQ-04` (outreach delivery, LLM provider, multi-org UI, baseline metric) — each has a stated default to build against until resolved.
