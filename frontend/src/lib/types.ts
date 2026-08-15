// Mirrors the backend canonical model (backend/app/canonical/models.py) plus the
// derived types LIENRHO owns: predictions, rule flags, agent findings, actions.
// Keep this file in sync when the backend canonical model changes.

export type PaymentStatus = "PENDING" | "PARTIALLY_PAID" | "PAID" | "OVERDUE";

export type Priority = "CRITICAL" | "HIGH" | "FOLLOW_UP";

// The Recovery Strategy agent's three outcomes (Track A/B/C).
export type RecommendedAction = "FOLLOW_UP" | "FINANCE" | "ESCALATE";

export type ApprovalState = "PENDING_APPROVAL" | "APPROVED" | "REJECTED";

export interface Invoice {
  invoiceId: string;
  customerId: string;
  customerName: string;
  invoiceAmount: number;
  invoiceDate: string;
  dueDate: string;
  paymentStatus: PaymentStatus;
  daysOverdue: number;
}

// XGBoost output: probability across the four delay buckets (FR-002).
export interface DelayPrediction {
  bucket_0_15: number;
  bucket_16_30: number;
  bucket_31_45: number;
  bucket_over_45: number;
}

// One human-readable contributing feature behind a prediction (FR-003).
export interface PredictionFactor {
  label: string;
  detail: string;
  direction: "increases_risk" | "decreases_risk";
}

// Deterministic rules-engine output (FR-005, FR-006) — never LLM-generated.
export interface RuleFlags {
  statutoryFlag: boolean;
  statutoryInterest: number | null;
  tredsEligible: boolean;
  tredsIneligibleReason: string | null;
}

// Receivables Investigator agent findings (FR-007).
export interface AgentFindings {
  paymentPromise: boolean;
  promisedDate: string | null;
  disputeDetected: boolean;
  confidence: number;
  evidence: string[];
}

// One row in the daily action queue (FR-009).
export interface ActionQueueItem {
  id: string;
  invoice: Invoice;
  priority: Priority;
  recommendedAction: RecommendedAction;
  reason: string;
  approvalState: ApprovalState;
  prediction: DelayPrediction;
}

// Full investigation view for a single invoice (FR-003, FR-007, FR-014).
export interface InvoiceInvestigation {
  invoice: Invoice;
  prediction: DelayPrediction;
  factors: PredictionFactor[];
  rules: RuleFlags;
  findings: AgentFindings;
  recommendedAction: RecommendedAction;
  reason: string;
  approvalState: ApprovalState;
  auditTrail: AuditEntry[];
}

// FR-014: what was recommended, why, who decided, what happened.
export interface AuditEntry {
  timestamp: string;
  decidedBy: "ML" | "RULES" | "AGENT" | "HUMAN";
  what: string;
  why: string;
}

// 30-day rolling forecast (FR-004) with the invoices driving any shortfall (FR-015).
export interface ForecastPoint {
  date: string;
  projectedCash: number;
}

export interface CashForecast {
  points: ForecastPoint[];
  cashThreshold: number;
  shortfallDate: string | null;
  shortfallAmount: number | null;
  contributingInvoices: ContributingInvoice[];
}

export interface ContributingInvoice {
  invoiceId: string;
  customerName: string;
  amount: number;
  contribution: number;
}
