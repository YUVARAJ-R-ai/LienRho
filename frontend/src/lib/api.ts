// API client. Replaces the mock accessors in mockData.ts.
//
// Screens are server components, so these run on the server and the browser
// never talks to the backend directly. `cache: "no-store"` keeps the action
// queue live — a stale queue is worse than a slow one for a screen whose whole
// job is telling you what to do right now.

import type {
  ActionQueueItem,
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
