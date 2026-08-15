// Mock data standing in for the API until the backend endpoints land.
// Numbers follow the reference demo scenario in prd.md §37/§16 (30 invoices,
// Rs 42.6L receivables, Rs 6.2L shortfall ~14 days out) so the UI matches the
// pitch. Swap this module for real fetches once the endpoints exist — the
// screens import the accessor functions, not the constants.

import type {
  ActionQueueItem,
  CashForecast,
  InvoiceInvestigation,
} from "./types";

export const actionQueue: ActionQueueItem[] = [
  {
    id: "AQ-001",
    invoice: {
      invoiceId: "INV-1042",
      customerId: "CUST-004",
      customerName: "Apex Trading",
      invoiceAmount: 210000,
      invoiceDate: "2026-06-10",
      dueDate: "2026-06-25",
      paymentStatus: "OVERDUE",
      daysOverdue: 52,
    },
    priority: "CRITICAL",
    recommendedAction: "ESCALATE",
    reason: "52 days overdue, 92% default probability, MSMED statutory threshold crossed",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.02,
      bucket_16_30: 0.02,
      bucket_31_45: 0.04,
      bucket_over_45: 0.92,
    },
  },
  {
    id: "AQ-002",
    invoice: {
      invoiceId: "INV-1038",
      customerId: "CUST-002",
      customerName: "Global Retail",
      invoiceAmount: 320000,
      invoiceDate: "2026-06-20",
      dueDate: "2026-07-20",
      paymentStatus: "OVERDUE",
      daysOverdue: 26,
    },
    priority: "CRITICAL",
    recommendedAction: "FINANCE",
    reason: "TReDS eligible, projected cash deficit in 2 days",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.1,
      bucket_16_30: 0.22,
      bucket_31_45: 0.38,
      bucket_over_45: 0.3,
    },
  },
  {
    id: "AQ-003",
    invoice: {
      invoiceId: "INV-1023",
      customerId: "CUST-001",
      customerName: "ABC Logistics",
      invoiceAmount: 480000,
      invoiceDate: "2026-07-01",
      dueDate: "2026-07-31",
      paymentStatus: "OVERDUE",
      daysOverdue: 17,
    },
    priority: "HIGH",
    recommendedAction: "FOLLOW_UP",
    reason: "Payment promised Friday, no dispute detected, long-standing customer",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.45,
      bucket_16_30: 0.33,
      bucket_31_45: 0.15,
      bucket_over_45: 0.07,
    },
  },
  {
    id: "AQ-004",
    invoice: {
      invoiceId: "INV-1051",
      customerId: "CUST-007",
      customerName: "Sunrise Textiles",
      invoiceAmount: 175000,
      invoiceDate: "2026-07-05",
      dueDate: "2026-08-04",
      paymentStatus: "OVERDUE",
      daysOverdue: 11,
    },
    priority: "HIGH",
    recommendedAction: "FOLLOW_UP",
    reason: "Customer average delay 27 days, no communication on file",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.3,
      bucket_16_30: 0.4,
      bucket_31_45: 0.2,
      bucket_over_45: 0.1,
    },
  },
  {
    id: "AQ-005",
    invoice: {
      invoiceId: "INV-1047",
      customerId: "CUST-005",
      customerName: "Nova Components",
      invoiceAmount: 96000,
      invoiceDate: "2026-07-12",
      dueDate: "2026-08-11",
      paymentStatus: "OVERDUE",
      daysOverdue: 4,
    },
    priority: "FOLLOW_UP",
    recommendedAction: "FOLLOW_UP",
    reason: "Recently overdue, customer historically pays within 15 days",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.68,
      bucket_16_30: 0.22,
      bucket_31_45: 0.07,
      bucket_over_45: 0.03,
    },
  },
  {
    id: "AQ-006",
    invoice: {
      invoiceId: "INV-1049",
      customerId: "CUST-006",
      customerName: "Meridian Foods",
      invoiceAmount: 143000,
      invoiceDate: "2026-07-15",
      dueDate: "2026-08-14",
      paymentStatus: "PENDING",
      daysOverdue: 1,
    },
    priority: "FOLLOW_UP",
    recommendedAction: "FOLLOW_UP",
    reason: "Just past due date, low predicted delay",
    approvalState: "PENDING_APPROVAL",
    prediction: {
      bucket_0_15: 0.74,
      bucket_16_30: 0.18,
      bucket_31_45: 0.06,
      bucket_over_45: 0.02,
    },
  },
];

const investigations: Record<string, InvoiceInvestigation> = {
  "INV-1042": {
    invoice: actionQueue[0].invoice,
    prediction: actionQueue[0].prediction,
    factors: [
      {
        label: "Days overdue",
        detail: "52 days — past the MSMED 45-day statutory threshold",
        direction: "increases_risk",
      },
      {
        label: "Customer average delay",
        detail: "41 days across 8 previous invoices",
        direction: "increases_risk",
      },
      {
        label: "Unanswered follow-ups",
        detail: "3 reminders sent, no reply in 21 days",
        direction: "increases_risk",
      },
    ],
    rules: {
      statutoryFlag: true,
      statutoryInterest: 18400,
      tredsEligible: false,
      tredsIneligibleReason: "Buyer does not participate in TReDS",
    },
    findings: {
      paymentPromise: false,
      promisedDate: null,
      disputeDetected: false,
      confidence: 0.88,
      evidence: [
        "3 reminder emails sent between 2026-07-10 and 2026-07-25, no response",
        "No dispute or quality complaint raised in any thread",
      ],
    },
    recommendedAction: "ESCALATE",
    reason:
      "Statutory threshold crossed at 52 days overdue with no payment promise and no dispute on record. Track C (statutory escalation).",
    approvalState: "PENDING_APPROVAL",
    auditTrail: [
      {
        timestamp: "2026-08-15T06:02:11Z",
        decidedBy: "ML",
        what: "Predicted 92% probability of >45 day delay",
        why: "Days overdue, customer average delay, unanswered follow-ups",
      },
      {
        timestamp: "2026-08-15T06:02:12Z",
        decidedBy: "RULES",
        what: "statutory_flag = true, interest = Rs 18,400",
        why: "check_msmed_threshold() — 52 days >= 45 day threshold, buyer conditions met",
      },
      {
        timestamp: "2026-08-15T06:02:15Z",
        decidedBy: "AGENT",
        what: "No payment promise, no dispute detected (confidence 0.88)",
        why: "Receivables Investigator analyzed 3 email threads",
      },
      {
        timestamp: "2026-08-15T06:02:16Z",
        decidedBy: "AGENT",
        what: "Recommended ESCALATE (Track C)",
        why: "Statutory threshold met, no promise, no dispute",
      },
    ],
  },
  "INV-1038": {
    invoice: actionQueue[1].invoice,
    prediction: actionQueue[1].prediction,
    factors: [
      {
        label: "Invoice value",
        detail: "Rs 3.2L — largest single contributor to the projected shortfall",
        direction: "increases_risk",
      },
      {
        label: "Customer payment pattern",
        detail: "Typically pays at 30–40 days",
        direction: "increases_risk",
      },
      {
        label: "TReDS participation",
        detail: "Buyer is a registered TReDS participant",
        direction: "decreases_risk",
      },
    ],
    rules: {
      statutoryFlag: false,
      statutoryInterest: null,
      tredsEligible: true,
      tredsIneligibleReason: null,
    },
    findings: {
      paymentPromise: false,
      promisedDate: null,
      disputeDetected: false,
      confidence: 0.71,
      evidence: ["Last contact 2026-07-28, acknowledged receipt, no date committed"],
    },
    recommendedAction: "FINANCE",
    reason:
      "TReDS-eligible and the single largest driver of the Rs 6.2L shortfall 14 days out. Financing closes the gap without straining the relationship. Track B.",
    approvalState: "PENDING_APPROVAL",
    auditTrail: [
      {
        timestamp: "2026-08-15T06:02:18Z",
        decidedBy: "ML",
        what: "Predicted 68% probability of delay beyond 30 days",
        why: "Customer payment pattern, invoice age",
      },
      {
        timestamp: "2026-08-15T06:02:19Z",
        decidedBy: "RULES",
        what: "treds_eligible = true",
        why: "check_treds_eligibility() — invoice approved, buyer participates",
      },
      {
        timestamp: "2026-08-15T06:02:22Z",
        decidedBy: "AGENT",
        what: "Recommended FINANCE (Track B)",
        why: "TReDS eligible, largest shortfall contributor, relationship intact",
      },
    ],
  },
  "INV-1023": {
    invoice: actionQueue[2].invoice,
    prediction: actionQueue[2].prediction,
    factors: [
      {
        label: "Payment promise on file",
        detail: "Customer committed to paying Friday 2026-08-21",
        direction: "decreases_risk",
      },
      {
        label: "Relationship duration",
        detail: "4 years, 22 invoices, no disputes",
        direction: "decreases_risk",
      },
      {
        label: "Days overdue",
        detail: "17 days past due",
        direction: "increases_risk",
      },
    ],
    rules: {
      statutoryFlag: false,
      statutoryInterest: null,
      tredsEligible: false,
      tredsIneligibleReason: "Invoice not yet buyer-approved",
    },
    findings: {
      paymentPromise: true,
      promisedDate: "2026-08-21",
      disputeDetected: false,
      confidence: 0.93,
      evidence: [
        'WhatsApp 2026-08-12: "We will clear this by Friday, payment is in process"',
      ],
    },
    recommendedAction: "FOLLOW_UP",
    reason:
      "Explicit payment promise for 2026-08-21 from a 4-year customer with no dispute history. Relationship-preserving reminder is enough. Track A.",
    approvalState: "PENDING_APPROVAL",
    auditTrail: [
      {
        timestamp: "2026-08-15T06:02:24Z",
        decidedBy: "ML",
        what: "Predicted 45% probability of payment within 15 days",
        why: "Payment promise, relationship duration, days overdue",
      },
      {
        timestamp: "2026-08-15T06:02:27Z",
        decidedBy: "AGENT",
        what: "Payment promise detected for 2026-08-21 (confidence 0.93)",
        why: "Receivables Investigator parsed WhatsApp thread",
      },
      {
        timestamp: "2026-08-15T06:02:28Z",
        decidedBy: "AGENT",
        what: "Recommended FOLLOW_UP (Track A)",
        why: "Promise on file, no dispute, high-value long-term customer",
      },
    ],
  },
};

export const cashForecast: CashForecast = {
  cashThreshold: 500000,
  shortfallDate: "2026-08-29",
  shortfallAmount: 620000,
  points: [
    { date: "2026-08-15", projectedCash: 1850000 },
    { date: "2026-08-17", projectedCash: 1720000 },
    { date: "2026-08-19", projectedCash: 1610000 },
    { date: "2026-08-21", projectedCash: 1890000 },
    { date: "2026-08-23", projectedCash: 1450000 },
    { date: "2026-08-25", projectedCash: 1120000 },
    { date: "2026-08-27", projectedCash: 780000 },
    { date: "2026-08-29", projectedCash: -120000 },
    { date: "2026-08-31", projectedCash: 240000 },
    { date: "2026-09-02", projectedCash: 610000 },
    { date: "2026-09-04", projectedCash: 950000 },
    { date: "2026-09-06", projectedCash: 1180000 },
    { date: "2026-09-08", projectedCash: 1340000 },
    { date: "2026-09-10", projectedCash: 1520000 },
    { date: "2026-09-13", projectedCash: 1710000 },
  ],
  contributingInvoices: [
    {
      invoiceId: "INV-1038",
      customerName: "Global Retail",
      amount: 320000,
      contribution: 320000,
    },
    {
      invoiceId: "INV-1042",
      customerName: "Apex Trading",
      amount: 210000,
      contribution: 210000,
    },
    {
      invoiceId: "INV-1051",
      customerName: "Sunrise Textiles",
      amount: 175000,
      contribution: 90000,
    },
  ],
};

export function getActionQueue(): ActionQueueItem[] {
  return actionQueue;
}

export function getInvestigation(invoiceId: string): InvoiceInvestigation | null {
  return investigations[invoiceId] ?? null;
}

export function getCashForecast(): CashForecast {
  return cashForecast;
}

// Portfolio totals shown on the dashboard header.
export function getPortfolioSummary() {
  const totalReceivables = 4260000;
  const atRisk = 1180000;
  return {
    totalReceivables,
    atRisk,
    openInvoices: 30,
    shortfallAmount: cashForecast.shortfallAmount,
    shortfallDate: cashForecast.shortfallDate,
  };
}
