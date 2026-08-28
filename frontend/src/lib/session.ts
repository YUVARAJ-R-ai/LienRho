// Where the access token lives on the frontend (#20).
//
// The token sits in an httpOnly cookie, so browser JavaScript cannot read it.
// That costs one indirection — mutating calls go through Next route handlers
// instead of straight to FastAPI — and buys the property that an XSS bug on
// any screen cannot exfiltrate a credential that grants access to the whole
// org's receivables.

import { cookies } from "next/headers";

export const SESSION_COOKIE = "lienrho_session";

// Matches the backend's jwt_ttl_minutes default (12h). A cookie outliving the
// token it carries just produces confusing 401s instead of a clean redirect.
export const SESSION_MAX_AGE_SECONDS = 12 * 60 * 60;

export const sessionCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  path: "/",
  // Only over HTTPS in production; leaving this on would break local http dev.
  secure: process.env.NODE_ENV === "production",
  maxAge: SESSION_MAX_AGE_SECONDS,
};

// `cookies()` is async in Next 16 — awaiting it is not optional.
export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}
