// Exchanges credentials for a session cookie (#20).
//
// The browser never sees the access token: this handler calls FastAPI, takes
// the token out of the response, and stores it httpOnly. The client form only
// ever learns whether the login succeeded.

import { NextResponse } from "next/server";
import { SESSION_COOKIE, sessionCookieOptions } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const { email, password } = await request.json();

  const upstream = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });

  if (!upstream.ok) {
    // Deliberately not forwarding the backend's message verbatim — it is the
    // same for a wrong password and an unknown account, and it should stay
    // that way on this side too.
    return NextResponse.json(
      { error: "Incorrect email or password" },
      { status: 401 },
    );
  }

  const data = await upstream.json();
  const response = NextResponse.json({
    orgId: data.org_id,
    email: data.email,
    displayName: data.display_name,
  });
  response.cookies.set(SESSION_COOKIE, data.access_token, sessionCookieOptions);
  return response;
}
