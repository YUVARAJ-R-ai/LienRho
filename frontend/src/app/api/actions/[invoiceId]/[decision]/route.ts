// Proxies the approval gate through the server so the token stays httpOnly
// (FR-010, #20).
//
// Approve/Reject are the only mutating calls in the app and they originate
// from a click, so they cannot be render-time fetches in a server component.
// Rather than hand the browser a token to call FastAPI with, the click goes to
// this same-origin handler, which attaches the session server-side.
//
// Status codes and the 409 body are passed through untouched: ApprovalPanel
// reads `failingConditions` off a TReDS refusal to tell the user which
// condition failed, and flattening that into a generic error would take away
// the only actionable part of the message.

import { NextResponse } from "next/server";
import { getSessionToken } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED = new Set(["approve", "reject"]);

export async function POST(
  request: Request,
  { params }: { params: Promise<{ invoiceId: string; decision: string }> },
) {
  const { invoiceId, decision } = await params;

  // Whitelist rather than interpolate: `decision` comes from the URL, and
  // passing it straight through would let a caller reach any path under
  // /api/actions/{id}/ on the backend.
  if (!ALLOWED.has(decision)) {
    return NextResponse.json({ error: "Unknown decision" }, { status: 404 });
  }

  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const upstream = await fetch(
    `${API_BASE}/api/actions/${encodeURIComponent(invoiceId)}/${decision}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );

  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
