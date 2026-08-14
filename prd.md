LIENRHO — Product Requirements Document (PRD)

Tagline: When invoices wait, cash shouldn’t.
Product: LIENRHO
Target: Indian MSMEs
Core idea: An intelligent working-capital decision layer that integrates with existing accounting/ERP software instead of replacing it.

This PRD consolidates the original hackathon research/problem statement with the decisions we made during our discussion. Where the research document specifies a technical or regulatory component, I preserve that design; the Tally/Zoho integration direction is our product decision discussed afterward, not something claimed by the source document.

1. Executive Summary

Indian MSMEs can have healthy sales and profits while still facing serious cash-flow problems because customers frequently pay invoices much later than the business needs the money. The resulting gap between accounts receivable and available cash creates working-capital stress, particularly when payroll, suppliers, rent, and other expenses become due before customers pay.

Existing accounting software primarily provides the financial system of record: invoices, payments, ledgers, reconciliation and reports. LIENRHO is not intended to replace those systems.

Instead, LIENRHO acts as an intelligence and action layer on top of them.

It connects to existing accounting/ERP systems such as TallyPrime, Zoho Books or, in the future, other ERP platforms; analyzes receivables and payment history; predicts payment delays; forecasts upcoming liquidity shortages; evaluates statutory and financing conditions; investigates unstructured communication; and recommends or executes the most appropriate action.

The central transformation is:

Existing accounting data
          ↓
      LIENRHO
          ↓
"What's going to happen?"
          ↓
"How will it affect our cash?"
          ↓
"What should we do?"
          ↓
"Execute that action."

The research document identifies this transition from passive financial records to an actionable daily queue as the core opportunity.

2. Problem Statement
2.1 The real-world problem

Consider an MSME with:

30 outstanding invoices
₹42.6 lakh in receivables
upcoming payroll and supplier obligations
customers with different payment behaviors

The business owner knows:

"People owe me ₹42.6 lakh."

But that doesn't answer:

Which customer will actually pay soon?
Which invoice is likely to be delayed?
How much cash will actually arrive in the next 7/14/30 days?
Will the company have enough cash for payroll?
Which invoice should the owner chase first?
Which invoice could be financed?
Which invoice may have crossed a statutory payment threshold?
Should the company preserve the customer relationship or escalate?
What evidence exists in emails/WhatsApp conversations?
What action should happen today?

The reference scenario explicitly models ₹42.6 lakh across 30 invoices, with ₹11.8 lakh identified as high-delay risk and a ₹6.2 lakh projected liquidity deficit within 14 days.

3. Product Vision
LIENRHO should answer one question every morning:

"Given everything this business is owed, its expected cash position, customer behavior and available financial options, what should the business do today?"

Instead of:

Invoice → Overdue → Reminder

LIENRHO creates:

Invoice
   ↓
Payment Risk
   ↓
Liquidity Impact
   ↓
Legal / Financing Eligibility
   ↓
Customer Context
   ↓
Optimal Action
   ↓
Execution
4. Target User
Primary user
MSME owner / finance manager

The person who currently has to manually coordinate:

accounting software
bank information
invoices
payment follow-ups
customer communications
financing
compliance
legal escalation

The research specifically frames the human operator as the manual bridge between fragmented financial systems.

5. What LIENRHO Is NOT

This is extremely important.

We are not building:

another Tally
another Zoho Books
another invoice generator
another bookkeeping application
another generic finance chatbot
an LLM that gives financial advice
a dashboard that simply displays overdue invoices

The accounting system remains the system of record.

LIENRHO is the:

Decision + intelligence + orchestration layer.

6. Product Architecture

The overall system will contain six major layers.

┌──────────────────────────────────────────────┐
│              EXISTING SYSTEMS                │
│ Tally │ Zoho │ ERP │ Bank │ Communication    │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 1. DATA INGESTION & NORMALIZATION            │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 2. ML CORE                                   │
│ Payment Delay Prediction + Cash Forecasting  │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 3. DETERMINISTIC RULES ENGINE                │
│ MSMED + TReDS + Financial Rules              │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 4. STATEFUL MULTI-AGENT REASONING            │
│ Investigation + Strategy                    │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 5. DECISION & EXECUTION ENGINE               │
│ Prioritization + Human Approval              │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│ 6. OUTREACH & FINANCIAL WORKFLOWS            │
│ WhatsApp │ Email │ TReDS │ Legal Dossier     │
└──────────────────────────────────────────────┘

This six-layer architecture follows the technical blueprint in the research document.

7. Layer 1 — Data Integration
Objective

Connect LIENRHO to the systems the business already uses.

Primary hackathon integration

TallyPrime

TallyPrime
    ↓
HTTP / JSON / XML
    ↓
LIENRHO Connector
Secondary integration

Zoho Books

Zoho Books
    ↓
OAuth + REST API
    ↓
LIENRHO Connector
Future connectors
SAP
Oracle
Microsoft Dynamics
ERPNext
Other accounting systems
Why connectors matter

We don't want:

"Export CSV → upload CSV to LIENRHO."

We want:

"Connect your accounting software → LIENRHO continuously understands your receivables."

The product therefore has:

                 LIENRHO CORE
                      │
          ┌───────────┼───────────┐
          ↓           ↓           ↓
        Tally       Zoho       ERPNext
      Connector    Connector   Connector
          │           │           │
          └───────────┼───────────┘
                      ↓
              Canonical Data Model

Every connector converts its source data into a common LIENRHO schema.

8. Canonical Financial Data Model

We need a standardized representation independent of the accounting platform.

Invoice
{
  "invoice_id": "INV-1023",
  "customer_id": "CUST-001",
  "invoice_amount": 480000,
  "invoice_date": "2026-07-01",
  "due_date": "2026-07-31",
  "acceptance_date": "2026-07-02",
  "payment_status": "OVERDUE",
  "payment_date": null
}
Customer
customer_id
customer_name
industry
customer_type
payment_history
average_delay
relationship_duration
TReDS_status
Payment history
invoice
due_date
actual_payment_date
days_delayed
payment_amount
payment_status
Business financial state
current_cash
expected_inflows
upcoming_expenses
payroll
supplier_payments
cash_threshold
9. Layer 2 — Payment Risk ML

This is where we make LIENRHO technically serious.

Objective

Predict when an invoice is likely to be paid rather than merely classifying it as overdue.

The proposed model is XGBoost trained on historical transaction features.

Output

Instead of:

Late: YES

we produce:

P(0–15 days)  = 12%
P(16–30 days) = 20%
P(31–45 days) = 28%
P(>45 days)   = 40%

The four prediction buckets are specified in the research architecture.

Features

Potential features:

invoice amount
invoice age
days overdue
customer payment history
average historical delay
number of previous late payments
payment promise history
customer category
invoice-to-average-invoice ratio
relationship duration
historical payment variance
dispute history
Explainability

Every prediction should have an explanation.

Example:

82% probability of >30-day delay

Because:

+ Customer average delay: 27 days
+ 4/6 previous invoices late
+ Current invoice already 18 days overdue
+ High invoice amount

This is important because finance users need defensible decisions, not black-box numbers.

10. Layer 2B — Cash-Flow Forecasting

Payment prediction alone isn't enough.

The same ₹5 lakh invoice can have completely different importance depending on the company's cash position.

Example
Current cash                ₹5L
Expected inflows            ₹8L
Upcoming expenses          ₹16L
                             
Projected shortage          ₹3L

LIENRHO needs to identify this before the shortage occurs.

The proposed architecture generates a 30-day rolling liquidity curve by comparing expected inflows with upcoming operational expenses.

11. Liquidity Risk

The system should calculate:

Current cash
+
Expected collections
+
Potential financing
-
Upcoming expenses
=
Projected liquidity

Then identify:

cash surplus
cash shortage
date of shortage
magnitude of shortage
invoices responsible for the risk

Example:

Cash deficit: ₹6.2L in 14 days

Now the system can ask:

"Which receivables can solve this?"

12. Layer 3 — Deterministic Rules Engine

This must NOT be handled by the LLM.

Financial/legal calculations need deterministic logic.

The research specifically separates statutory rules from LLM reasoning.

MSMED Act Rule Engine

The system checks relevant invoice dates, buyer information and MSME status.

For the reference architecture:

If overdue >= 45 days
AND relevant buyer conditions are satisfied
→ statutory flag

The research specifies the 45-day threshold and statutory interest treatment in its proposed workflow.

TReDS Eligibility

Example:

Invoice approved = TRUE
AND
Buyer participates in TReDS
AND
Other eligibility conditions satisfied

→

TReDS financing opportunity

The reference architecture explicitly includes this deterministic eligibility check.

13. Layer 4 — Multi-Agent Investigation

This is where the LLM belongs.

Not in calculations.

Not in statutory rules.

Not in payment prediction.

Instead, agents handle unstructured information and contextual reasoning.

Agent 1 — Receivables Investigator

Input:

WhatsApp
Email
Customer communication
Payment history
Invoice information

Finds:

payment promises
excuses
disputes
missing documents
manager approval
delivery issues
customer sentiment/context

Example:

"Payment will be cleared by Friday after manager approval."

Agent extracts:

{
  "payment_promise": true,
  "promised_date": "...",
  "dispute_detected": false,
  "confidence": 0.91
}

The reference scenario uses exactly this kind of communication investigation.

14. Agent 2 — Recovery Strategy Agent

This agent receives:

ML risk
+
cash urgency
+
legal status
+
customer relationship
+
communication evidence

Then chooses the appropriate strategy.

Track A — Relationship-preserving recovery

Use when:

important customer
payment likely
no major dispute
legal escalation would damage relationship

Action:

Contextual payment reminder.

Track B — Financing

Use when:

business needs cash urgently
invoice is eligible
financing is economically sensible

Action:

TReDS financing workflow.

Track C — Statutory escalation

Use when:

chronic non-payment
statutory conditions satisfied
repeated promises broken
no genuine dispute

Action:

Prepare legal/statutory dossier.

These three tracks are explicitly defined in the reference design.

15. Decision Engine

This is arguably the heart of LIENRHO.

The system shouldn't ask:

"Which invoice is most overdue?"

It should ask:

"Which action creates the greatest useful financial outcome right now?"

Potential decision factors:

Payment probability
+
Cash-flow urgency
+
Invoice value
+
Days overdue
+
Legal urgency
+
Financing availability
+
Financing cost
+
Customer relationship importance
+
Recovery probability

Output:

ACTION = FINANCE
PRIORITY = CRITICAL

or:

ACTION = FOLLOW_UP
PRIORITY = HIGH

or:

ACTION = ESCALATE
PRIORITY = CRITICAL
16. Daily Action Queue

This is what the user actually sees.

Instead of a giant invoice table:

INV001
INV002
INV003
INV004
...

LIENRHO displays:

🔴 Critical

₹2.1L — Apex Trading

52 days overdue
92% default probability
Statutory threshold crossed

→ Prepare escalation

🟠 Cash Urgent

₹3.2L — Global Retail

TReDS eligible
Cash deficit in 2 days

→ Finance invoice

🟡 Follow Up

₹4.8L — ABC Logistics

17 days overdue
Payment promised Friday

→ Send reminder

This action queue is a central requirement of the reference architecture.

17. Layer 6 — Outreach

Once a strategy has been selected, LIENRHO generates the relevant communication.

Email
Professional formal reminder
WhatsApp
Short conversational reminder
Vernacular

Potentially:

English
Hindi
Tamil
Hinglish

The research specifically proposes localized/vernacular communication generation.

18. Human-in-the-Loop

LIENRHO should recommend and prepare actions, but sensitive financial/legal actions should require approval in the MVP.

Example:

LIENRHO:


Recommended:
FINANCE ₹3.2L invoice


Reason:
Cash deficit in 48 hours
TReDS eligible


[Approve Financing] [Reject]

Or:

Recommended:
Send payment reminder


[Send] [Edit] [Cancel]

This gives us autonomous workflow without pretending that an AI should independently make irreversible financial/legal decisions.

The reference architecture specifically emphasizes autonomous execution with human overrides.

19. TReDS Integration

TReDS is one of the most important financial integrations.

The concept:

MSME has invoice
       ↓
Corporate buyer owes money later
       ↓
MSME needs cash now
       ↓
Invoice discounting
       ↓
Immediate liquidity

For the hackathon:

MVP

We create a TReDS sandbox/mock connector.

LIENRHO generates:

{
  "invoice_id": "INV-1085",
  "amount": 320000,
  "buyer": "Global Retail",
  "due_date": "...",
  "financing_required": true
}

Then simulate:

Eligible ✓
Financing rate
Estimated proceeds
Estimated financing cost

The research's demonstration includes automated preparation of a TReDS bill-discounting payload.

20. Legal / MSMED Workflow

For eligible chronic defaults:

LIENRHO assembles:

Udyam information
+
Invoice
+
Payment history
+
Proof of delivery
+
Communication evidence
+
Interest calculation
+
Required documentation

into:

Statutory escalation dossier

The reference scenario proposes assembling such a dossier for MSME Samadhaan ODR.

For the hackathon, this should be a document-generation/simulation workflow, not an uncontrolled automatic legal filing.

21. Integration Architecture
Core principle
LIENRHO does not replace accounting software.
               EXISTING BUSINESS
                      │
          ┌───────────┼───────────┐
          ↓           ↓           ↓
        Tally        Zoho       ERP
          │           │           │
          └───────────┼───────────┘
                      ↓
              LIENRHO CONNECTORS
                      ↓
             NORMALIZED DATA
                      ↓
               LIENRHO CORE

This gives us a scalable product architecture.

22. Tally Integration
Primary Indian MSME connector

For the hackathon:

TallyPrime
    ↓
HTTP / JSON/XML
    ↓
FastAPI Connector
    ↓
LIENRHO

We should initially focus on reading:

invoices
customers
payment records
ledgers
relevant financial information

Later:

LIENRHO
    ↓
Tally

can be used for approved write-back workflows.

23. Zoho Integration

Secondary SaaS connector:

Zoho Books
     ↓
OAuth
     ↓
REST API
     ↓
LIENRHO

This demonstrates that LIENRHO isn't tied to one accounting vendor.

24. Unified Connector Interface

Backend abstraction:

class AccountingConnector:


    def get_invoices():
        pass


    def get_customers():
        pass


    def get_payments():
        pass


    def get_expenses():
        pass


    def create_task():
        pass

Implement:

TallyConnector
ZohoConnector
ERPNextConnector

All return the same internal schema.

25. Recommended Tech Stack

Based on the architecture we're discussing:

Frontend

Next.js + React

For:

dashboard
action queue
invoice investigation
financial graphs
approval screens
Backend

FastAPI + Python

For:

APIs
ML inference
connectors
rules engine
orchestration
Database

PostgreSQL

Store:

normalized invoices
customers
payment history
predictions
agent state
actions
audit logs
ML

Python

XGBoost
scikit-learn
time-series forecasting

The research specifically proposes XGBoost/Prophet/scikit-learn for the ML layer.

Agent orchestration

LangGraph

For:

Investigator
      ↓
Strategy
      ↓
Execution

The research specifically recommends stateful graph architecture to enforce controlled execution paths.

Structured agent outputs

Pydantic

Every agent should return structured JSON rather than arbitrary prose.

Example:

{
  "risk": "HIGH",
  "payment_promise": true,
  "dispute": false,
  "recommended_action": "FOLLOW_UP",
  "confidence": 0.91
}
LLM

Use the LLM for:

communication parsing
document investigation
strategy reasoning
message generation
multilingual communication

Do NOT use it for:

interest calculation
payment probability
statutory thresholds
financial arithmetic
cash-flow calculations

This separation is a core architectural principle of the source proposal.

26. Data Flow

Complete end-to-end flow:

                    TALLY / ZOHO
                         │
                         ↓
                Data Ingestion API
                         │
                         ↓
                 Normalization
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
       Payment History        Current Invoices
              │                     │
              └──────────┬──────────┘
                         ↓
                  XGBoost Model
                         │
                         ↓
                Payment Risk Score
                         │
                         ↓
                 Cash Forecaster
                         │
                         ↓
                Liquidity Position
                         │
                         ↓
                 Rules Engine
                         │
             ┌───────────┴───────────┐
             ↓                       ↓
         MSMED Check             TReDS Check
             │                       │
             └───────────┬───────────┘
                         ↓
                  Agentic Layer
                         │
                ┌────────┴────────┐
                ↓                 ↓
          Investigator       Strategy Agent
                │                 │
                └────────┬────────┘
                         ↓
                  Decision Engine
                         ↓
                  Action Queue
                         ↓
              Human Approval
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
     WhatsApp          TReDS          Legal Dossier
27. Core User Journey
Step 1 — Connect accounting system
Connect TallyPrime
Step 2 — LIENRHO synchronizes data
Invoices
Customers
Payments
Outstanding receivables
Step 3 — Risk analysis
30 invoices
₹42.6L outstanding


4 high-risk invoices
₹11.8L at risk
Step 4 — Liquidity analysis
Cash deficit expected:
₹6.2L in 14 days
Step 5 — Rules
1 invoice → statutory concern
3 invoices → financing opportunity
Step 6 — Agents investigate

Agent discovers:

"Customer promised payment Friday."

Another:

"Invoice approved and TReDS eligible."

Another:

"Three payment promises broken."

Step 7 — Strategy
Invoice A → Follow up
Invoice B → Finance
Invoice C → Escalate
Step 8 — Action

User sees:

TODAY'S ACTIONS


🔴 Finance ₹3.2L
🟠 Escalate ₹2.1L
🟡 Follow up ₹4.8L


[Review Actions]
28. Main Dashboard
Header
LIENRHO


Cash Position
₹5.8L


Projected 14-Day Gap
₹6.2L


Outstanding Receivables
₹42.6L
Risk overview
HIGH RISK       4 invoices
MEDIUM RISK     8 invoices
LOW RISK       18 invoices
Action queue
CRITICAL
────────────────────────


₹3.2L  → Finance
₹2.1L  → Escalate


HIGH
────────────────────────


₹4.8L  → Follow up
₹1.7L  → Follow up
29. Invoice Investigation Screen

Clicking an invoice should show:

INV-1023


₹4,80,000
17 days overdue


Payment probability
68%


Expected delay
20 days


Customer history
Average delay: 26 days

Then:

Evidence
WhatsApp
"Payment will be cleared Friday..."


Disputes
None detected


Previous promises
3
Recommendation
FOLLOW UP


Reason:
High-value customer
Payment promise exists
No dispute
Legal escalation not justified
30. Cash Forecast Screen

Graph:

Cash
 ₹
 │      ╭────
 │     ╱
 │────╯
 │          ╲
 │           ╲____
 │
 └────────────────── Days
        ↑
     deficit

Display:

Cash deficit predicted in 14 days


Amount: ₹6.2L


Main contributors:
₹4.8L delayed invoice
₹3.2L pending supplier payment
₹2.0L payroll
31. Explainability & Audit Trail

Every important recommendation needs:

What?

Finance INV-1085

Why?

Cash deficit in 48 hours + TReDS eligible.

Evidence?
Invoice approved
Buyer verified
Due date
Cash forecast
Financing cost
Who decided?
ML
Rules Engine
Agent
Human approval
What happened?
Action approved
Submission generated

This makes the system defensible.

32. Security Requirements

Because financial data is sensitive:

Authentication
OAuth where applicable
JWT/session authentication
Authorization

Users only see their organization.

Secrets

API credentials stored securely.

Data isolation
Organization A
    ≠
Organization B
Audit logs

Record:

who
did what
when
using which recommendation
33. LLM Safety Architecture

The LLM should never have unrestricted access.

Instead:

Agent
  ↓
Structured tool call
  ↓
Validation
  ↓
Deterministic service
  ↓
Result

Example:

LLM says:
"Calculate MSMED interest."


       ↓


NOT:
LLM performs calculation


       ↓


YES:
LLM calls:


calculate_interest(
    principal,
    delay_days,
    RBI_rate
)


       ↓


Deterministic Python function
34. MVP Scope

We must not try to build everything.

For the hackathon MVP, I recommend:

Must Have

✅ Tally connector
✅ Synthetic/realistic MSME invoice dataset
✅ Canonical data model
✅ XGBoost payment-delay model
✅ 30-day cash-flow forecast
✅ MSMED rule engine
✅ TReDS eligibility engine
✅ 2–3 LangGraph agents
✅ Prioritized action queue
✅ Explainable recommendations
✅ Human approval
✅ WhatsApp/email message generation
✅ TReDS mock submission
✅ Legal dossier generation

35. Should Have

🟡 Zoho connector
🟡 Multilingual Tamil/Hinglish communication
🟡 Better forecasting
🟡 Customer relationship score
🟡 What-if analysis

Example:

"What happens if I finance ₹5L?"

36. Future Scope

Not necessary for the hackathon:

Account Aggregator integration
GSTIN verification
real TReDS transaction execution
automated banking actions
additional ERP connectors
full legal portal submission
advanced reinforcement learning
credit scoring
supplier financing
MNC ERP integrations

The research identifies AA, GSTIN, TReDS and other institutional rails as future/deeper integration opportunities.

37. Demo Dataset

We'll create a realistic portfolio.

30 invoices

Total:

₹42.6L

Include deliberately constructed cases:

Case A
₹4.8L
17 days overdue
68% further-delay probability
Payment promised Friday

→ Relationship-preserving follow-up

Case B
₹3.2L
Due in 10 days
TReDS eligible
Cash deficit in 48 hours

→ Finance

Case C
₹2.1L
52 days overdue
92% default probability
3 broken promises

→ Statutory escalation

These scenarios directly follow the reference case study.

38. Key Metrics

We need measurable outcomes.

Financial

DSO reduction

Target demonstration:

14–21 day improvement

The reference proposal uses this as an impact metric.

Liquidity
₹ amount of liquidity unlocked
Risk
High-risk invoices identified
Operational
Manual review time
        ↓
Automated prioritization
Recovery
Receivables recovered
39. Technical Evaluation Metrics

We should also measure the models.

ML
Precision
Recall
F1
ROC-AUC
calibration
bucket accuracy
Forecasting
MAE
RMSE
Agents
structured-output validity
tool-call success
decision consistency
System
API latency
connector reliability
workflow completion rate
40. What Makes LIENRHO Technically Strong

This is our answer when someone says:

"Isn't this just an AI dashboard?"

No.

                LIENRHO
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
      ML         Rules      Agents
        │          │          │
  Prediction   Compliance  Investigation
        │          │          │
        └──────────┼──────────┘
                   ↓
              Optimization
                   ↓
              Execution

The research explicitly argues against generic LLM wrappers and favors this hybrid architecture.

41. What Makes LIENRHO Economically Strong

The economics story is:

Revenue ≠ Cash


Profitability
     ↓
Receivables
     ↓
Payment delay
     ↓
Liquidity gap
     ↓
Working-capital stress

LIENRHO connects:

Accounts Receivable → Payment Risk → Liquidity → Financing → Recovery

That is the economic core of the product.

42. Product Positioning
Don't say:

"AI-powered invoice management."

Too generic.

Say:

"LIENRHO is a working-capital intelligence layer that plugs into existing accounting systems and turns unpaid receivables into prioritized financial actions."

Or shorter:

"LIENRHO turns receivables data into working-capital decisions."

43. One-Line Pitch

LIENRHO connects to the accounting system an MSME already uses, predicts which receivables are likely to be delayed, forecasts the resulting cash-flow impact, and determines whether each critical invoice should be collected, financed, or escalated.

44. The Demo Story

This should be the entire hackathon presentation narrative.

Scene 1 — Before LIENRHO

Show:

30 invoices
₹42.6L outstanding

Messy spreadsheet.

Ask:

"Which ₹6.2L do I need to recover before payroll?"

Scene 2 — Connect
Connect TallyPrime
        ↓
Sync
Scene 3 — Analysis

LIENRHO processes everything.

₹42.6L receivables


₹11.8L high risk


₹6.2L projected liquidity gap


₹8.2L TReDS opportunity


₹4.8L statutory concern

The reference case uses these exact portfolio-level values.

Scene 4 — Three invoices

Click ABC Logistics.

LIENRHO finds the payment promise.

→ Reminder.

Click Global Retail.

LIENRHO sees cash shortage + financing eligibility.

→ TReDS.

Click Apex Trading.

LIENRHO sees repeated broken promises + statutory condition.

→ Legal dossier.

Scene 5 — Final screen
BEFORE LIENRHO


₹42.6L receivables
No prioritization
Manual follow-up
Unknown liquidity risk




AFTER LIENRHO


₹11.8L high-risk identified
₹6.2L liquidity gap identified
3 financing opportunities
1 statutory escalation
Prioritized action queue
45. The Core Product Philosophy

The most important principle for the team:

Don't build an AI that talks about financial data. Build an AI system that does something with financial data.

Therefore:

LLM
     ≠
Product


LLM
 +
ML
 +
Rules
 +
Financial Data
 +
Connectors
 +
Agents
 +
Execution
     =
LIENRHO

The source research describes the fundamental opportunity as a coordination problem across fragmented financial systems, rather than simply a lack of financial data.

46. Final Technical Scope

If we freeze the architecture today, I'd define LIENRHO as:

Frontend
└── Next.js / React


Backend
└── FastAPI


Database
└── PostgreSQL


Accounting Integration
├── TallyPrime       ← PRIMARY
└── Zoho Books       ← SECONDARY


ML
├── XGBoost
└── Time-series forecasting


Rules
├── MSMED
├── TReDS
└── Financial eligibility


Agents
├── Receivables Investigator
├── Recovery Strategy Agent
└── Execution Agent


Orchestration
└── LangGraph


Validation
└── Pydantic


Communication
├── Email
├── WhatsApp simulation
└── Vernacular generation


Financial Workflows
├── TReDS mock
└── MSME legal dossier


UI
├── Cash dashboard
├── Risk dashboard
├── Action queue
├── Invoice investigation
├── Cash forecast
└── Approval workflow
47. Final Definition of LIENRHO
LIENRHO
When invoices wait, cash shouldn’t.

LIENRHO is an intelligent working-capital decision layer for MSMEs. It integrates with existing accounting systems, analyzes receivables and payment behavior, predicts payment delays, forecasts liquidity shortages, applies deterministic financial and statutory rules, investigates customer communications using stateful AI agents, and recommends or prepares the optimal action—collection, financing, or escalation.

The important distinction is:

Tally/Zoho records what happened.

LIENRHO determines what should happen next.

That is the product we're building.
