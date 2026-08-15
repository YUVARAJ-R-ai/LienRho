# ID Registry
Append-only. Never reuse or renumber an ID, even if the item is withdrawn.

## STK
STK-01  MSME owner / finance manager (primary user)  (added 2026-08-14)
STK-02  Customer (buyer/debtor)  (added 2026-08-14)
STK-03  Financier / TReDS platform  (added 2026-08-14)
STK-04  Legal / statutory system (MSME Samadhaan)  (added 2026-08-14)
STK-05  Development team (ML, Backend, Agents, Frontend roles)  (added 2026-08-14)
STK-06  Hackathon judges/evaluators  (added 2026-08-14)

## BR
BR-MSMED     Statutory flag on invoices overdue >= 45 days, deterministic  (added 2026-08-14)
BR-TREDS     TReDS eligibility, deterministic  (added 2026-08-14)
BR-APPROVAL  No FINANCE/ESCALATE/outreach-send without explicit human approval  (added 2026-08-14)
BR-TENANT    Every table carries org_id, scoped at the data-access layer  (added 2026-08-14)

## FR
FR-001  Ingest and normalize accounting data  (added 2026-08-14)
FR-002  Predict payment-delay probability per invoice  (added 2026-08-14)
FR-003  Explain each payment-delay prediction  (added 2026-08-14)
FR-004  Forecast 30-day cash position  (added 2026-08-14)
FR-005  Apply MSMED statutory threshold check  (added 2026-08-14)
FR-006  Evaluate TReDS financing eligibility  (added 2026-08-14)
FR-007  Investigate customer communications  (added 2026-08-14)
FR-008  Recommend a recovery strategy per invoice  (added 2026-08-14)
FR-009  Prioritize actions into a daily action queue  (added 2026-08-14)
FR-010  Require human approval before executing sensitive actions  (added 2026-08-14)
FR-011  Generate draft outreach messages  (added 2026-08-14)
FR-012  Generate a mock TReDS financing submission  (added 2026-08-14)
FR-013  Generate a statutory escalation dossier  (added 2026-08-14)
FR-014  Record an audit trail for every recommendation and action  (added 2026-08-14)
FR-015  Identify invoices contributing to a projected shortfall  (added 2026-08-14)

## NFR
NFR-001  Organization data isolation  (added 2026-08-14)
NFR-002  Connector credential secrecy  (added 2026-08-14)
NFR-003  Deterministic statutory/financial computation  (added 2026-08-14)
NFR-004  Action queue render latency (p95 <= 3.0s @ 100 invoices)  (added 2026-08-14)
NFR-005  Payment-delay model quality (ROC-AUC >= 0.75, ECE <= 0.10)  (added 2026-08-14)
NFR-006  Connector extensibility  (added 2026-08-14)
NFR-007  Decision traceability  (added 2026-08-14)
NFR-008  Recommendation explainability  (added 2026-08-14)

## UC
<!-- none assigned yet -->

## US
<!-- none assigned yet -->

## CON
CON-01  Stack fixed: Next.js/React, FastAPI/Python, PostgreSQL, XGBoost/scikit-learn, LangGraph, Pydantic  (added 2026-08-14)
CON-02  TallyPrime primary connector (hard); Zoho secondary (soft)  (added 2026-08-14)
CON-03  Build/demo window: a few days to 2 weeks  (added 2026-08-14)
CON-04  Team of 3-5 across ML, Backend/connectors, Agents, Frontend  (added 2026-08-14)
CON-05  LLM never performs statutory/financial/interest arithmetic  (added 2026-08-14)
CON-06  Sensitive/irreversible actions require human approval in the MVP  (added 2026-08-14)
CON-07  TReDS integration is sandbox/mock only, not a live financial transaction  (added 2026-08-14)
CON-08  Legal/MSMED workflow produces a dossier only, no automated filing  (added 2026-08-14)

## ASM
ASM-01  TallyPrime exposes an HTTP/XML gateway reachable from a FastAPI connector during dev  (added 2026-08-14)
ASM-02  Synthetic 30-invoice/Rs42.6L dataset substitutes for real transaction history  (added 2026-08-14)
ASM-03  WhatsApp/email outreach in the MVP is drafted/simulated in-UI, not sent live  (added 2026-08-14)
ASM-04  An external LLM API is reachable from the backend for the agent layer  (added 2026-08-14)
ASM-05  Multi-tenant isolation is needed even for a single-MSME hackathon demo  (added 2026-08-14)

## RSK
<!-- none assigned yet -->

## IF
<!-- none assigned yet -->

## ADR
ADR-001  Modular monolith over microservices  (added 2026-08-14)
ADR-002  LLM never computes statutory or financial values  (added 2026-08-14)
ADR-003  Tech stack accepted as a fixed constraint, not re-derived  (added 2026-08-14)

## OQ
OQ-01  Is WhatsApp/email outreach live-sent or drafted-in-UI only for the MVP?  (added 2026-08-14)
OQ-02  Which LLM provider/model powers the agent layer?  (added 2026-08-14)
OQ-03  Is multi-tenant org isolation needed for the hackathon demo, or single-org only?  (added 2026-08-14)
OQ-04  What is the actual baseline time an MSME owner spends triaging receivables today?  (added 2026-08-14)
