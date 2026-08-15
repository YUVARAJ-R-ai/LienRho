# LIENRHO

**When invoices wait, cash shouldn't.**

LIENRHO is a working-capital decision layer for Indian MSMEs (Micro, Small & Medium Enterprises). It plugs into the accounting software an MSME already uses — TallyPrime first, Zoho Books second — and turns raw receivables data into a single daily answer:

> Given everything this business is owed, its expected cash position, customer behavior, and available financial options — what should the business do today?

It is **not** an accounting app, **not** a bookkeeping/invoicing tool, and **not** a generic finance chatbot. Tally/Zoho remain the system of record. LIENRHO only owns *derived* data: predictions, forecasts, rule-engine flags, agent findings, decisions, actions, and audit logs.

> **Status: pre-code / planning phase.** This repo currently holds the product spec, architecture, and research that back the build — see [Project status](#project-status) below. There is no application code yet.

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
├── README.md                                   — this file
├── prd.md                                       — full Product Requirements Document
├── docs/
│   ├── inception.md                             — formal inception doc: stakeholders, scope,
│   │                                               constraints, FRs/NFRs, architecture, ADRs, open questions
│   ├── _id-registry.md                          — append-only ledger of every STK/FR/NFR/CON/ADR/... ID
│   └── presentation/                            — pitch deck (.pptx)
├── indian_agentic_finance_hackathon_research.md — market research behind the product choice
└── .claude/skills/lienrho-context/SKILL.md      — domain/architecture context for AI-assisted development
```

## Requirements & design docs

| Doc | Purpose |
|---|---|
| [`docs/inception.md`](docs/inception.md) | Source of truth: stakeholders, scope/anti-goals, constraints (`CON-nn`), assumptions (`ASM-nn`), functional requirements (`FR-nnn`), non-functional requirements (`NFR-nnn`), architecture, ADRs, open questions (`OQ-nn`) |
| [`prd.md`](prd.md) | The original, more narrative product requirements document |
| [`indian_agentic_finance_hackathon_research.md`](indian_agentic_finance_hackathon_research.md) | Research comparing candidate hackathon ideas and why the receivables-recovery direction won |
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

This repo currently contains the **inception and requirements phase** output only — no application code. The next step is scaffolding the modular-monolith skeleton described above (FastAPI service + module boundaries, Next.js frontend, Postgres schema) so each role can start building against a shared interface. Track progress via the repo's Issues/Project board.

## License

Not yet decided.
