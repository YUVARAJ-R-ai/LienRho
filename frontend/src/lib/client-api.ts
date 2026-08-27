// Browser-side API calls (#20).
//
// Split from api.ts because that module reads the session cookie through
// `next/headers`, which cannot exist in a client bundle. Everything here runs
// after a user interaction, so it goes to this app's own route handlers —
// same-origin, no token in the browser, the handler attaches it server-side.

import type { ApprovalResult, Artifact } from "./types";

const SESSION_EXPIRED = "Your session has expired. Sign in again to continue.";

// Draft a reminder (FR-011). Not gated on approval — the draft is what the
// user reads in order to decide, so requiring approval to see it would invert
// the review step. Sending is their own action in their own client (OQ-01).
export async function getDraft(
  invoiceId: string,
  channel: "EMAIL" | "WHATSAPP" = "EMAIL",
): Promise<Artifact> {
  const response = await fetch(
    `/api/invoice/${invoiceId}/draft?channel=${channel}`,
  );
  if (response.status === 401) throw new Error(SESSION_EXPIRED);
  if (!response.ok) throw new Error(`draft failed: ${response.status}`);
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
  const response = await fetch(`/api/actions/${invoiceId}/${path}`, {
    method: "POST",
  });

  if (response.status === 401) throw new Error(SESSION_EXPIRED);

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
