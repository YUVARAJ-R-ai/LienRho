// API client. Replaces the mock accessors in mockData.ts.
//
// Screens are server components, so these run on the server and the browser
// never talks to the backend directly. `cache: "no-store"` keeps the action
// queue live — a stale queue is worse than a slow one for a screen whose whole
// job is telling you what to do right now.
//
// Server-only: it reads the httpOnly session cookie through `next/headers`, so
// importing it from a client component breaks the build. Browser-side calls
// live in client-api.ts and go through this app's route handlers instead (#20).
//
// Every /api call now carries a bearer token read from the httpOnly session
// cookie (#20). Reading it here rather than at each call site means a new
// accessor cannot forget it — the same reasoning that puts the org filter in
// the backend's data-access layer instead of in each endpoint.

import { getSessionToken } from "./session";
import type {
  ActionQueueItem,
  Artifact,
  CashForecast,
  InvoiceInvestigation,
  PortfolioSummary,
} from "./types";

export type { PortfolioSummary };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Thrown when the session is missing or the backend rejects the token. The
// proxy redirects unauthenticated navigation, so reaching this means the token
// expired part-way through a session.
export class NotAuthenticated extends Error {
  constructor() {
    super("Not authenticated");
    this.name = "NotAuthenticated";
  }
}

async function authorizedFetch(path: string, init: RequestInit = {}) {
  const token = await getSessionToken();
  if (!token) throw new NotAuthenticated();

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });

  if (response.status === 401) throw new NotAuthenticated();
  return response;
}

async function get<T>(path: string): Promise<T> {
  const response = await authorizedFetch(path);
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
  const response = await authorizedFetch(`/api/invoice/${invoiceId}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`investigation failed: ${response.status}`);
  }
  return response.json() as Promise<InvoiceInvestigation>;
}

// Re-read the artifact an approved action produced. Returns null when the
// action has not been approved (409) — an approved dossier must survive a
// reload, but an unapproved one must still not exist.
export async function getArtifact(invoiceId: string): Promise<Artifact | null> {
  const response = await authorizedFetch(`/api/invoice/${invoiceId}/artifact`);
  if (response.status === 409 || response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`artifact failed: ${response.status}`);
  }
  return response.json() as Promise<Artifact>;
}
