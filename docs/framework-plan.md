# LIENRHO — starting framework plan

Status: **Phases 0–4 largely built.** This describes the repo layout and build order for the modular monolith in `docs/inception.md` §6.

Per-requirement state lives in [`implementation-status.md`](implementation-status.md); demo sequencing in [`demo-checkpoints.md`](demo-checkpoints.md). Phase annotations below record what actually happened, including where the original ordering turned out to be wrong.

## Proposed top-level layout

```
LienRho/
├── backend/                  — FastAPI service (single deployable)
│   ├── app/
│   │   ├── connectors/       — AccountingConnector interface + TallyConnector, ZohoConnector
│   │   ├── canonical/        — Pydantic canonical data model (Invoice, Customer, Payment History, ...)
│   │   ├── ml_core/          — XGBoost payment-delay model, cash-flow forecasting
│   │   ├── rules_engine/     — MSMED threshold + TReDS eligibility, deterministic only
│   │   ├── agents/           — LangGraph: Investigator, Strategy, Execution; tool-call schemas
│   │   ├── decision_engine/  — prioritization + PENDING_APPROVAL/APPROVED/REJECTED gate
│   │   ├── outreach/         — message drafts, mock TReDS submission, dossier generation
│   │   ├── api/              — FastAPI routers, one per screen/resource
│   │   └── db/                — SQLAlchemy models + Alembic migrations, org_id scoping helpers
│   └── tests/                — mirrors app/ by module
├── frontend/                 — Next.js app
│   └── app/
│       ├── dashboard/        — action queue
│       ├── invoice/[id]/     — investigation screen
│       ├── forecast/         — cash forecast screen
│       └── approvals/        — approval queue
├── data/                     — synthetic demo dataset (30 invoices / Rs 42.6L), model training data
├── docs/                     — existing spec docs (inception.md, this file, ADRs, id-registry)
└── prd.md, README.md, CONTRIBUTING.md
```

This mirrors `NFR-006` (a new connector or module should never require touching another module) and the four team roles named in `docs/inception.md` §6.

## Build order

Dependencies matter more than role here — several modules can't be usefully tested without a working canonical dataset first.

**Phase 0 — Foundation** ✅ done
Backend skeleton, frontend skeleton, Postgres schema + migrations, canonical Pydantic models, CI. These have no dependencies on each other and can start simultaneously. Everything downstream blocks on the canonical data model existing (even as a stub).

**Phase 1 — Data in** ✅ done (synthetic; Tally connector deferred)
`TallyConnector` (or the synthetic dataset as a stand-in if the Tally gateway spike in `ASM-01` doesn't land quickly) + the synthetic 30-invoice/Rs 42.6L dataset. Until invoices exist in the canonical store, ML has nothing to train on, rules have nothing to evaluate, and the frontend has nothing to render — so this is the critical path, not a "backend task" to sequence last.

**Phase 2 — Independent core logic** ✅ done
- ML: XGBoost delay model + explainability, cash-flow forecast
- Backend: MSMED rules engine, TReDS eligibility engine
- Frontend: build dashboard/investigation/forecast screens against a mocked API response shape (agreed contract, not the real endpoints) so frontend isn't blocked on backend completion

**Phase 3 — Agents + Decision Engine** 🟡 decision engine done, agents blocked on `OQ-02`
Receivables Investigator and Recovery Strategy agents need the rules engine and ML outputs available as tool calls (`ADR-002` — the agent never computes them itself). The Decision Engine then combines ML + rules + agent output into the ranked queue with the approval gate.

**Phase 4 — Execution + audit trail** 🟡 audit trail built (in memory); outreach/dossier outstanding
Outreach draft generation, mock TReDS submission, dossier generation, and the audit log — all naturally come after the Decision Engine exists to approve/reject actions.

**Phase 5 — Integration + demo hardening** 🟡 frontend wired to the live API; latency check and rehearsal outstanding
Wire the frontend to real endpoints (replacing Phase 2's mocked contract), latency check against `NFR-004` (p95 <= 3.0s @ 100 invoices), and demo-script rehearsal against the reference scenario in `prd.md` §37.

## Mapping to the issue tracker

Each Phase 0-4 item above corresponds 1:1 to one of the 19 issues already filed (`Line` field: Frontend/Backend/Database/ML/Agents/Infra) and can be moved through the project board's `Iteration 1`-`4` columns roughly matching these phases. Phase 5 doesn't have a filed issue yet — it's integration work best scoped once Phases 1-4 are further along, not upfront.

## What this plan deliberately does not decide

- Exact API contracts between frontend and backend (that's a Phase 0/1 conversation between whoever owns frontend and backend, not something to lock in a planning doc)
- Which of Tally connector vs. synthetic dataset comes first if `ASM-01`'s spike is inconclusive — flagged as a risk, not resolved here
- Anything blocked on `OQ-01`-`OQ-04` (see `docs/inception.md` §8) — build against the stated defaults until those are answered


## What the plan got wrong

Worth recording, since the same mistakes are easy to repeat:

- **Frontend was not blocked on the backend.** Building the screens against a typed mock module and swapping the accessor imports later cost one commit. The indirection paid for itself.
- **The ML phase was under-scoped.** Training data quality turned out to matter more than model tuning: the first generator leaked the label and would have produced a meaningless ROC-AUC. Budget time for *how the data is made*, not just for fitting (ADR-004).
- **Correctness bugs surfaced only when real numbers flowed end to end**, not in unit tests — the forecast counting elapsed delay buckets as incoming cash, and financing keyed off the wrong condition. Wiring a thin slice all the way through early is what exposed them.
- **Several tests encoded the bugs they were meant to catch.** Three forecast tests asserted an invoice could be both 20 days overdue and certain to pay within 0–15 days. Fixtures need the same scrutiny as the code.
