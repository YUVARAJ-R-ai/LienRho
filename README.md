<div align="center">

# 🧾 LIENRHO

### The working-capital decision layer for Indian MSMEs

**When invoices wait, cash shouldn't.**
Your accounting system says *what you're owed*.
LIENRHO says *what to do about it today*.

![python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)
![next.js](https://img.shields.io/badge/next.js-16-000000?logo=nextdotjs&logoColor=white)
![fastapi](https://img.shields.io/badge/fastapi-async-009688?logo=fastapi&logoColor=white)
![postgres](https://img.shields.io/badge/postgres-16-4169E1?logo=postgresql&logoColor=white)
![ml](https://img.shields.io/badge/ml-XGBoost-EB4C42)
![agents](https://img.shields.io/badge/agents-LangGraph-1C3C3C)

[Quickstart](#quickstart) · [The Problem](#the-problem) · [How It Works](#what-lienrho-does) · [Architecture](#architecture) · [Scope](#scope) · [Docs](#requirements--design-docs)

</div>

---

LIENRHO plugs into the accounting software an MSME already uses — TallyPrime first, Zoho Books second — and turns raw receivables data into a single daily answer:

> Given everything this business is owed, its expected cash position, customer behavior, and available financial options — what should the business do today?

It is **not** an accounting app, **not** a bookkeeping/invoicing tool, and **not** a generic finance chatbot. Tally/Zoho remain the system of record. LIENRHO only owns *derived* data: predictions, forecasts, rule-engine flags, agent findings, decisions, actions, and audit logs.

> **Status: working vertical slice.** The pipeline runs end to end — synthetic portfolio → XGBoost delay predictions → deterministic MSMED/TReDS checks → probabilistic cash forecast → ranked action queue → UI, every recommendation carrying its audit trail. The LangGraph agents, the Tally connector, and the outreach/dossier generators are not built yet — see [Project status](#project-status).

## Quickstart

Start the backend first — the frontend reads from it.

**Backend** — needs Docker for Postgres:

```bash
cd backend
docker compose up -d          # starts Postgres on :5432
uv sync                       # installs dependencies
uv run alembic upgrade head   # creates the schema
uv run python -m app.ml_core.train     # trains the delay model (CUDA, falls back to CPU)
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

The API degrades to rule-only recommendations if no trained model artifact exists, so it still starts before you train. `./run-dev.sh start|stop|status` runs it detached at low priority if you'd rather not hold a terminal.

**Frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

## The problem

An MSME owner can see "customers owe me ₹42.6L," but Tally/Zoho don't answer the questions that actually decide the business's next move:

- Which invoice will actually be paid, and when?
- Will there be enough cash for payroll and suppliers in 14 days?
- Which invoice should be chased first — and which should be financed or escalated instead?
- Has an invoice crossed the MSMED Act's statutory payment threshold?
- What do the WhatsApp/email threads with this customer actually say?

Today the owner is the manual bridge between the accounting system, bank position, customer conversations, financing options (TReDS), and statutory rules — cross-referenced by hand, every day.

## What LIENRHO does

```
Existing accounting data (Tally / Zoho)
        │
        ▼
  Payment-delay prediction  (XGBoost, 4 delay buckets, explainable)
        │
        ▼
  30-day cash-flow forecast  (liquidity gap detection)
        │
        ▼
  Statutory + financing rules  (MSMED 45-day threshold, TReDS eligibility — deterministic)
        │
        ▼
  Agent investigation  (WhatsApp/email evidence, recovery strategy: Follow-up / Finance / Escalate)
        │
        ▼
  Prioritized, explainable Action Queue  (Critical / High / Follow Up)
        │
        ▼
  Human approval  →  outreach draft / mock TReDS submission / legal dossier
```

### The one rule the whole architecture is built around

**The LLM never computes a statutory, financial, or interest value.** MSMED thresholds, TReDS eligibility, and interest calculations are deterministic Python functions (`calculate_interest()`, `check_msmed_threshold()`, `check_treds_eligibility()`, …). LangGraph agents call these as structured tool calls and never generate the number themselves. Every agent call returns a Pydantic-validated object — unvalidated free-text output never reaches the Decision Engine. See `ADR-002` in [`docs/inception.md`](docs/inception.md).

The second rule: **nothing sensitive executes without a human.** Financing submissions, statutory escalation, and outreach sends all sit in `PENDING_APPROVAL` until an authorized user explicitly approves or rejects them (`BR-APPROVAL`, `FR-010`).

## Architecture

Modular monolith: one FastAPI backend with module boundaries mirroring four team roles, plus a separate Next.js frontend. Microservices were considered and rejected — nothing in this build needs independent scaling, and splitting a small team's sub-2-week build into separate services would spend the whole timeline on integration plumbing (`ADR-001`).

```
Web Client (Next.js)
  → LIENRHO API (FastAPI, single deployable)
      Connectors module      (Backend)   — Tally/Zoho adapters
      Canonical data layer   (Backend)
      ML Core module         (ML)        — XGBoost payment-delay model + cash forecast
      Rules Engine module    (Backend)   — MSMED + TReDS, deterministic only
      Agent orchestration    (Agents)    — LangGraph: Investigator, Strategy, Execution
      Decision Engine        (Backend+Agents) — prioritization + approval gate
      Outreach/document mod  (Backend)   — message drafts, TReDS mock, dossier
  → PostgreSQL (canonical data, predictions, agent state, actions, audit log)
```

**Stack (fixed, `CON-01`):** Next.js/React · FastAPI/Python · PostgreSQL · XGBoost/scikit-learn · LangGraph · Pydantic.

## Scope

**In scope for the MVP:**
- TallyPrime connector (read invoices, customers, payments, ledgers) + canonical data model
- XGBoost payment-delay model (4 buckets) with explainability
- 30-day rolling cash-flow forecast + liquidity-gap detection
- MSMED statutory threshold engine + TReDS eligibility engine (both deterministic)
- LangGraph agents: Receivables Investigator, Recovery Strategy, Execution
- Prioritized action queue with human-in-the-loop approval
- Draft WhatsApp/email reminders, mock TReDS submission, legal/MSMED dossier generation

**Explicitly out of scope for this build:** Zoho connector (deferred, secondary), multilingual generation, live TReDS execution, automated legal filing, Account Aggregator/GSTIN integration, automated banking actions, additional ERP connectors (SAP/Oracle/ERPNext), credit scoring, reinforcement learning.

Full detail, acceptance criteria, and rationale: [`docs/inception.md`](docs/inception.md) §3.

## Repository layout

```
.
├── backend/                     — FastAPI service (single deployable)
│   ├── app/
│   │   ├── connectors/          — AccountingConnector interface; Tally/Zoho adapters
│   │   ├── canonical/           — Pydantic canonical data model
│   │   ├── ml_core/             — XGBoost payment-delay model, cash forecasting
│   │   ├── rules_engine/        — MSMED + TReDS checks, deterministic only
│   │   ├── agents/              — LangGraph agents + tool-call schemas
│   │   ├── decision_engine/     — prioritization + approval gate
│   │   ├── outreach/            — message drafts, TReDS mock, dossier
│   │   ├── api/                 — FastAPI routers
│   │   └── db/                  — ORM models, migrations, org scoping
│   ├── migrations/              — Alembic
│   └── docker-compose.yml       — local Postgres
├── frontend/                    — Next.js App Router + shadcn/ui
│   └── src/
│       ├── app/                 — action queue, invoice, forecast, approvals routes
│       ├── components/          — shared UI
│       └── lib/                 — types, formatters, mock data
├── docs/
│   ├── inception.md             — stakeholders, scope, constraints, FRs/NFRs, ADRs, open questions
│   ├── implementation-status.md — per-requirement state: built vs. specified
│   ├── model-card.md            — model metrics, features, limitations
│   ├── demo-checkpoints.md      — phased plan,every checkpoint independently demoable
│   ├── framework-plan.md        — repo layout + build-phase ordering
│   ├── _id-registry.md          — append-only ledger of every STK/FR/NFR/CON/ADR/... ID
│   └── presentation/            — pitch deck (.pptx)
├── prd.md                       — full Product Requirements Document
├── CONTRIBUTING.md              — workflow, module ownership, non-negotiable rules
└── indian_agentic_finance_hackathon_research.md — research behind the product choice
```

## Requirements & design docs

| Doc | Purpose |
|---|---|
| [`docs/inception.md`](docs/inception.md) | Source of truth: stakeholders, scope/anti-goals, constraints (`CON-nn`), assumptions (`ASM-nn`), functional requirements (`FR-nnn`), non-functional requirements (`NFR-nnn`), architecture, ADRs, open questions (`OQ-nn`) |
| [`prd.md`](prd.md) | The original, more narrative product requirements document |
| [`indian_agentic_finance_hackathon_research.md`](indian_agentic_finance_hackathon_research.md) | Research comparing candidate hackathon ideas and why the receivables-recovery direction won |
| [`docs/implementation-status.md`](docs/implementation-status.md) | Per-FR/NFR state — what's actually built vs. specified |
| [`docs/model-card.md`](docs/model-card.md) | Model metrics, features, explainability approach, and limitations |
| [`docs/demo-checkpoints.md`](docs/demo-checkpoints.md) | Phased build plan where every checkpoint is independently demoable |
| [`docs/framework-plan.md`](docs/framework-plan.md) | Repo layout, build-phase ordering, and what that ordering got wrong |
| [`docs/_id-registry.md`](docs/_id-registry.md) | Append-only registry of every requirement/decision ID ever assigned — IDs are never reused or renumbered |

If `docs/inception.md` and `prd.md` ever disagree, `docs/inception.md` is authoritative (it explicitly supersedes narrative sections of the PRD where they diverge).

## Key domain terms

| Term | Meaning |
|---|---|
| MSME | Micro, Small & Medium Enterprise — Indian regulatory classification under the MSMED Act |
| DSO | Days Sales Outstanding — target: reduce by 14–21 days |
| MSMED Act | Governs mandatory payment timelines to MSME suppliers and statutory interest on delay; source of the 45-day overdue threshold |
| TReDS | Trade Receivables Discounting System — RBI-regulated invoice financing platform. LIENRHO only ever produces a **mock** submission |
| Action Queue | The prioritized Critical/High/Follow-Up list of recommended actions — the primary daily-use screen |
| Delay Bucket | XGBoost output: probability across 0–15 / 16–30 / 31–45 / >45 days overdue |
| Track A/B/C | Recovery Strategy agent's three outcomes: A = relationship-preserving follow-up, B = financing, C = statutory escalation |

Full glossary: [`docs/inception.md`](docs/inception.md) §1.

## Open questions

These affect design and are not yet resolved (see `docs/inception.md` §8 for defaults if left unresolved):

- **OQ-01** — Is outreach actually sent (WhatsApp Business API / SMTP), or drafted-in-UI only for the MVP?
- **OQ-02** — Which LLM provider/model powers the agent layer?
- **OQ-03** — Is a multi-org UI needed, or just the `org_id` schema field?
- **OQ-04** — What's the real baseline time an MSME owner spends triaging receivables today?

## Team roles

| Role | Owns |
|---|---|
| ML | Payment-delay model (XGBoost), cash forecasting |
| Backend / connectors | Tally/Zoho adapters, canonical data model, rules engine, outreach/document generation |
| Agents / LLM orchestration | LangGraph agents, Pydantic schemas, the tool-call boundary (`ADR-002`) |
| Frontend | Dashboard, action queue, investigation, forecast, and approval screens |

## Project status

| Area | Status |
|---|---|
| Backend skeleton + module boundaries | ✅ Done |
| Canonical data model (Pydantic + ORM) | ✅ Done |
| Postgres schema, migrations, org scoping | ✅ Done |
| MSMED + TReDS rules engines | ✅ Done |
| Synthetic demo dataset | ✅ Done |
| XGBoost delay model + explainability | ✅ Done |
| Cash-flow forecast + shortfall contributors | ✅ Done |
| Decision engine + approval gate | ✅ Done |
| API endpoints | ✅ Done |
| Frontend: 4 screens, wired to live API | ✅ Done |
| Audit trail (in-memory) | ✅ Done |
| LangGraph agents | ⬜ Not started |
| Tally connector | ⬜ Not started |
| Outreach, mock TReDS, dossier | ⬜ Not started |
| Audit trail persistence to Postgres | ⬜ Not started |

The pipeline runs end to end: synthetic portfolio → XGBoost predictions → deterministic MSMED/TReDS checks → probabilistic cash forecast → ranked action queue → UI, with every recommendation carrying its ML/Rules/Agent audit trail.

**Model quality (held-out, NFR-005 gate: PASS)** — ROC-AUC 0.834, expected calibration error 0.031, bucket accuracy 62.3% against a 25% four-class baseline. That figure is deliberately not near-perfect: the generator draws delays from a multi-factor latent process and the customer's average delay is computed from observed history, so the model has to learn a real relationship rather than recover a constant it was handed.

Build order and phase dependencies: [`docs/framework-plan.md`](docs/framework-plan.md).

**Two things to know before building on this:**

- Auth is stubbed. `backend/app/db/scoping.py` trusts an unverified `X-Org-Id` header, so NFR-001 does not hold yet — the scoping helper is right, the identity feeding it isn't. Don't expose this beyond local dev (#20).
- The frontend's `src/lib/types.ts` mirrors the backend response shapes by hand. Nothing enforces they stay in sync (#21).
- The action queue reads the synthetic portfolio, not a live Tally sync. Swapping it means changing `_load_portfolio()` in `backend/app/decision_engine/service.py` and nothing else (#6).
- Agent findings on the investigation screen are returned empty rather than fabricated, since the Receivables Investigator isn't built (#12).
- Approvals are in-memory and reset on restart; persistence is outstanding.

## License

Not yet decided.
