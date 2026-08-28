// The frontend/backend contract (#21).
//
// These used to be hand-written to mirror the backend's response models, with
// nothing enforcing that they stayed in sync — a renamed field shipped as an
// `undefined` on a screen rather than as a build failure.
//
// Every type here is now an alias onto `api-types.ts`, which is generated from
// the API's own OpenAPI schema (`backend/openapi.json`). The names and doc
// comments stay because they are what the components read and because
// `components["schemas"]["ActionQueueItemOut"]` says nothing about what an
// action queue item *is*. What changed is where the field lists come from.
//
// To change a shape: edit the Pydantic model, then run `npm run generate:types`
// (which regenerates the schema and these types together). CI fails on drift.

import type { components } from "./api-types";

type Schemas = components["schemas"];

// Unions the generator widens to `string`, kept narrow here because the
// components switch on them. Each is checked against the schema's own enum
// below, so a value added on the backend fails the build rather than silently
// falling through a switch.
export type PaymentStatus = "PENDING" | "PARTIALLY_PAID" | "PAID" | "OVERDUE";

export type Priority = "CRITICAL" | "HIGH" | "FOLLOW_UP";

// The Recovery Strategy agent's three outcomes (Track A/B/C).
export type RecommendedAction = "FOLLOW_UP" | "FINANCE" | "ESCALATE";

export type ApprovalState = "PENDING_APPROVAL" | "APPROVED" | "REJECTED";

export type ArtifactKind = "REMINDER" | "TREDS_SUBMISSION" | "DOSSIER";

export type AuditActor = "ML" | "RULES" | "TOOL" | "AGENT" | "HUMAN";

// One invoice as the API returns it.
export type Invoice = Omit<Schemas["InvoiceOut"], "paymentStatus"> & {
  paymentStatus: PaymentStatus;
};

// XGBoost output: probability across the four delay buckets (FR-002).
export type DelayPrediction = Schemas["DelayPredictionOut"];

// One human-readable contributing feature behind a prediction (FR-003).
export type PredictionFactor = Omit<Schemas["PredictionFactorOut"], "direction"> & {
  direction: "increases_risk" | "decreases_risk";
};

// Deterministic rules-engine output (FR-005, FR-006) — never LLM-generated.
export type RuleFlags = Schemas["RuleFlagsOut"];

// Receivables Investigator agent findings (FR-007).
export type AgentFindings = Schemas["AgentFindingsOut"];

// FR-014: what was recommended, why, who decided, what happened.
export type AuditEntry = Omit<Schemas["AuditEntryOut"], "decidedBy"> & {
  decidedBy: AuditActor;
};

// One row in the daily action queue (FR-009).
export type ActionQueueItem = Omit<
  Schemas["ActionQueueItemOut"],
  "invoice" | "priority" | "recommendedAction" | "approvalState" | "prediction"
> & {
  invoice: Invoice;
  priority: Priority;
  recommendedAction: RecommendedAction;
  approvalState: ApprovalState;
  prediction: DelayPrediction;
};

// Full investigation view for a single invoice (FR-003, FR-007, FR-014).
export type InvoiceInvestigation = Omit<
  Schemas["InvestigationOut"],
  | "invoice"
  | "factors"
  | "recommendedAction"
  | "approvalState"
  | "auditTrail"
  | "prediction"
  | "rules"
  | "findings"
> & {
  invoice: Invoice;
  prediction: DelayPrediction;
  factors: PredictionFactor[];
  rules: RuleFlags;
  findings: AgentFindings;
  recommendedAction: RecommendedAction;
  approvalState: ApprovalState;
  auditTrail: AuditEntry[];
};

// A generated execution artifact (FR-011, FR-012, FR-013). One shape for all
// three — the screen renders contentMarkdown without needing to know whether
// it holds a reminder, a financing submission, or a legal filing.
export type Artifact = Omit<Schemas["ArtifactOut"], "kind"> & {
  kind: ArtifactKind;
};

// The outcome of a human decision (FR-010). `artifact` is null on rejection —
// refusing an action must not hand back what it would have produced.
export type ApprovalResult = Omit<
  Schemas["ApprovalResultOut"],
  "approvalState" | "recommendedAction" | "artifact" | "auditTrail"
> & {
  approvalState: ApprovalState;
  recommendedAction: RecommendedAction;
  artifact: Artifact | null;
  auditTrail: AuditEntry[];
};

// 30-day rolling forecast (FR-004) with the invoices driving any shortfall (FR-015).
export type ForecastPoint = Schemas["ForecastPointOut"];

export type ContributingInvoice = Schemas["ContributingInvoiceOut"];

export type CashForecast = Omit<
  Schemas["CashForecastOut"],
  "points" | "contributingInvoices"
> & {
  points: ForecastPoint[];
  contributingInvoices: ContributingInvoice[];
};

export type PortfolioSummary = Schemas["PortfolioSummaryOut"];

// --------------------------------------------------------------- drift guards
//
// The narrowed types above are written as `Omit<Schema, "field"> & { field: … }`.
// `Omit` accepts keys the source type does not have, so if the backend renamed
// one of those fields the Omit would quietly do nothing and our replacement
// would ride along as an extra property — drift the compiler would not catch.
//
// Indexing the schema type by that key closes the hole: the lookups below stop
// compiling the moment a field is renamed or removed, and each `extends` check
// fails if the backend widens a union past what the components handle.

type Assert<T extends true> = T;

export type _DriftGuards = [
  Assert<PaymentStatus extends Schemas["InvoiceOut"]["paymentStatus"] ? true : false>,
  Assert<Priority extends Schemas["ActionQueueItemOut"]["priority"] ? true : false>,
  Assert<
    RecommendedAction extends Schemas["ActionQueueItemOut"]["recommendedAction"]
      ? true
      : false
  >,
  Assert<
    ApprovalState extends Schemas["ActionQueueItemOut"]["approvalState"] ? true : false
  >,
  Assert<ArtifactKind extends Schemas["ArtifactOut"]["kind"] ? true : false>,
  Assert<AuditActor extends Schemas["AuditEntryOut"]["decidedBy"] ? true : false>,
  Assert<
    PredictionFactor["direction"] extends Schemas["PredictionFactorOut"]["direction"]
      ? true
      : false
  >,
];
