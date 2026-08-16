// API client. Replaces the mock accessors in mockData.ts.
//
// Screens are server components, so these run on the server and the browser
// never talks to the backend directly. `cache: "no-store"` keeps the action
// queue live — a stale queue is worse than a slow one for a screen whose whole
// job is telling you what to do right now.

import type {
  ActionQueueItem,
  ApprovalResult,
  Artifact,
  CashForecast,
  InvoiceInvestigation,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PortfolioSummary {
  totalReceivables: number;
  atRisk: number;
  openInvoices: number;
  shortfallAmount: number | null;
  shortfallDate: string | null;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getActionQueue(): Promise<ActionQueueItem[]> {
  return get<ActionQueueItem[]>("/api/action-queue");
}

export function getPortfolioSummary(): Promise<PortfolioSummary> {
  return get<PortfolioSummary>("/api/summary");
}

export function getCashForecast(): Promise<CashForecast> {
  return get<CashForecast>("/api/forecast");
}

export async function getInvestigation(
  invoiceId: string,
): Promise<InvoiceInvestigation | null> {
  const response = await fetch(`${API_BASE}/api/invoice/${invoiceId}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`investigation failed: ${response.status}`);
  }
  return response.json() as Promise<InvoiceInvestigation>;
}

// Draft a reminder (FR-011). Not gated on approval — this is what the user
// reads in order to decide, so requiring approval to see it would invert the
// review step. Sending is their own action in their own client (OQ-01).
export function getDraft(
  invoiceId: string,
  channel: "EMAIL" | "WHATSAPP" = "EMAIL",
): Promise<Artifact> {
  return get<Artifact>(`/api/invoice/${invoiceId}/draft?channel=${channel}`);
}

// Re-read the artifact an approved action produced. Returns null when the
// action has not been approved (409) — an approved dossier must survive a
// reload, but an unapproved one must still not exist.
export async function getArtifact(invoiceId: string): Promise<Artifact | null> {
  const response = await fetch(`${API_BASE}/api/invoice/${invoiceId}/artifact`, {
    cache: "no-store",
  });
  if (response.status === 409 || response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`artifact failed: ${response.status}`);
  }
  return response.json() as Promise<Artifact>;
}

// The approval gate (FR-010, CON-06). These are the only mutating calls in the
// app, and they run from the browser rather than a server component — the user
// clicking Approve is the event, so it cannot be a render-time fetch.
export async function decideOnAction(
  invoiceId: string,
  approved: boolean,
): Promise<ApprovalResult> {
  const path = approved ? "approve" : "reject";
  const response = await fetch(`${API_BASE}/api/actions/${invoiceId}/${path}`, {
    method: "POST",
  });

  if (!response.ok) {
    // 409 means the decision stands but the artifact could not be produced —
    // a TReDS-ineligible invoice, most likely. Surface which condition failed
    // rather than a generic error the user can do nothing with.
    if (response.status === 409) {
      const body = await response.json().catch(() => null);
      const conditions = body?.detail?.failingConditions as string[] | undefined;
      throw new Error(
        conditions?.length
          ? `Cannot generate submission: ${conditions.join("; ")}`
          : "Cannot generate submission for this invoice.",
      );
    }
    throw new Error(`${path} failed: ${response.status}`);
  }

  return response.json() as Promise<ApprovalResult>;
}
