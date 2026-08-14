---
name: lienrho-context
description: Domain glossary, business rules, constraints, and coding conventions for LIENRHO — the MSME working-capital decision layer that plugs into TallyPrime/Zoho. Use whenever writing, reviewing, or discussing any LIENRHO code or design: connectors, the canonical data model, the XGBoost payment-risk/forecast layer, the MSMED/TReDS rules engine, the LangGraph agents (Investigator/Strategy/Execution), the decision engine, or the action-queue UI. Also consult before proposing an architectural change, adding a dependency, or answering "why does LIENRHO do X this way."
---

# LIENRHO project context

Derived from: `docs/inception.md` (Lite-tier inception, v1, 2026-08-14). If that file has since diverged from what's below, trust the file and update this skill in the same change.

LIENRHO is **not** an accounting app and **not** a generic finance chatbot. It's a decision + intelligence + orchestration layer that sits on top of TallyPrime/Zoho: Tally/Zoho stay the system of record for invoices, customers, payments, and ledgers; LIENRHO owns only *derived* data — predictions, forecasts, rule flags, agent findings, decisions, actions, audit logs. If a change would make LIENRHO write back financial transactions or duplicate bookkeeping, stop and check FR/CON scope in `docs/inception.md` §3 first — that's very likely out of scope.

## The one architectural rule that overrides convenience

**The LLM never computes a statutory, financial, or interest value.** MSMED thresholds, TReDS eligibility, and interest calculations are deterministic Python functions (`calculate_interest()`, `check_msmed_threshold()`, `check_treds_eligibility()`, ...). LangGraph agents call these as structured tool calls and never generate the number themselves (CON-05, NFR-003, ADR-002). If you're about to have an LLM prompt "calculate X" for anything statutory or financial — don't; write or call the deterministic function instead, and make sure the audit trail records which function produced the value.

The corollary for every agent: **structured I/O only.** Every LangGraph agent call returns a Pydantic-validated object; unvalidated/free-text output is never passed to the Decision Engine.

## Domain glossary

| Term | Definition |
|---|---|
| MSME | Micro, Small & Medium Enterprise — Indian regulatory classification under the MSMED Act |
| DSO | Days Sales Outstanding — average days to collect payment after a sale. Target: reduce by 14–21 days |
| Receivables / AR | Money owed to the business by customers for invoiced goods/services |
| MSMED Act | Governs mandatory payment timelines to MSME suppliers and statutory interest on delay. The system's 45-day overdue threshold comes from here |
| TReDS | Trade Receivables Discounting System — RBI-regulated platform for MSMEs to discount invoices to financiers for early payment. LIENRHO only ever produces a **mock** TReDS submission (CON-07) |
| Statutory escalation | Formal legal/regulatory path (MSME Samadhaan ODR) triggered when MSMED delay conditions are met. LIENRHO generates a dossier **document only** — never files automatically (CON-08) |
| Canonical Data Model | LIENRHO's internal normalized schema (Invoice, Customer, Payment History, Business Financial State — see `docs/inception.md` for fields) that every connector maps into |
| Connector | Adapter implementing `get_invoices() / get_customers() / get_payments() / get_expenses() / create_task()` against one accounting/ERP system. Adding a new one must touch nothing outside its own module (NFR-006) |
| Action Queue | The prioritized, ranked list (Critical / High / Follow Up) of recommended actions — the primary daily-use screen (NFR-004: p95 ≤ 3.0s render at ≤100 invoices) |
| Delay Bucket | XGBoost model's probability distribution across four buckets: 0–15, 16–30, 31–45, >45 days |
| Liquidity Gap | A point in the 30-day rolling cash forecast where projected cash falls below the cash threshold |
| Track A/B/C | Recovery Strategy agent's three outcomes: A = relationship-preserving follow-up, B = financing, C = statutory escalation |

## Business rules

- **BR-MSMED** — An invoice is flagged `statutory_flag=true` iff overdue ≥ 45 days AND buyer conditions are satisfied (deterministic, not LLM). Boundary: 44 days = false, 45 days = true.
- **BR-TREDS** — An invoice is TReDS-eligible iff invoice is approved AND the buyer participates in TReDS AND other eligibility conditions hold (deterministic).
- **BR-APPROVAL** — No FINANCE, ESCALATE, or outreach-send action executes until a human explicitly approves it (`[Approve]/[Reject]` or `[Send]/[Edit]/[Cancel]`). Rejecting leaves invoice state unchanged (FR-010, CON-06). This is the one place autonomy stops — do not add a code path that skips it, even for "obviously safe" cases.
- **BR-TENANT** — Every table carries `org_id`; every query is scoped to the authenticated user's org at the data-access layer, not left to individual endpoint authors (NFR-001).

## Constraints that shape every design choice

| ID | Constraint |
|---|---|
| CON-01 | Stack is fixed: Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic. Don't propose alternatives — evaluate within this stack (ADR-003) |
| CON-02 | TallyPrime is the primary connector (hard); Zoho is secondary/deferred (soft) |
| CON-03 | Build window: a few days to 2 weeks. Bias toward the MVP scope in `docs/inception.md` §3, not the Should-Have list |
| CON-05 | LLM never does statutory/financial arithmetic (see above) |
| CON-06 | Sensitive actions require human approval (see BR-APPROVAL) |
| CON-07 | TReDS is a mock/sandbox connector — never a live financial transaction |
| CON-08 | Legal dossier is generated for manual filing — never auto-submitted |

## Architecture at a glance

Modular monolith: one FastAPI service with module boundaries mirroring the four team roles, plus a separate Next.js frontend (ADR-001 — microservices were considered and rejected; no driver demands independent scaling on this team/timeline).

```
Web Client (Next.js)
  → LIENRHO API (FastAPI, single deployable)
      Connectors module      (Backend)   — Tally/Zoho adapters
      Canonical data layer   (Backend)
      ML Core module         (ML)        — XGBoost + forecasting
      Rules Engine module    (Backend)   — MSMED + TReDS, deterministic only
      Agent orchestration    (Agents)    — LangGraph: Investigator, Strategy, Execution
      Decision Engine        (Backend+Agents) — prioritization + approval gate
      Outreach/document mod  (Backend)   — message drafts, TReDS mock, dossier
  → PostgreSQL (canonical data, predictions, agent state, actions, audit log)
```

Role ownership: **ML** = payment-delay model + cash forecast. **Backend/connectors** = Tally/Zoho adapters, canonical model, rules engine, outreach/document generation. **Agents/LLM orchestration** = LangGraph agents, Pydantic schemas, the tool-call boundary in ADR-002. **Frontend** = dashboard, action queue, investigation, forecast, and approval screens.

## Where to look for more

- Full FR/NFR catalog, acceptance criteria, ADRs, open questions, assumptions register: `docs/inception.md`
- Open questions that affect design decisions before you build around them: OQ-01 (is outreach actually sent, or drafted-only?), OQ-02 (which LLM provider?), OQ-03 (is multi-org UI needed, or just the schema field?)
- ID scheme if you add or change a requirement: `STK-nn / CON-nn / ASM-nn / FR-nnn / NFR-nnn / ADR-nnn / OQ-nn` — IDs are permanent, never renumber; mark dead ones `Status: Withdrawn` instead.
