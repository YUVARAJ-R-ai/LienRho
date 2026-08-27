// Proxies the reminder draft to the browser with the session attached (#20).
//
// ApprovalPanel fetches the draft from the client — it is what the user reads
// in order to decide, and the panel loads it in response to a choice rather
// than at render time. The token is httpOnly, so the request has to pass
// through the server to be authorized.
//
// Not gated on approval (FR-011, OQ-01): the gate stands in front of *sending*,
// and requiring approval to read a draft would invert the review step.

import { NextResponse } from "next/server";
import { getSessionToken } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHANNELS = new Set(["EMAIL", "WHATSAPP"]);

export async function GET(
  request: Request,
  { params }: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await params;
  const requested = new URL(request.url).searchParams.get("channel") ?? "EMAIL";
  const channel = CHANNELS.has(requested) ? requested : "EMAIL";

  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const upstream = await fetch(
    `${API_BASE}/api/invoice/${encodeURIComponent(invoiceId)}/draft?channel=${channel}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );

  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
