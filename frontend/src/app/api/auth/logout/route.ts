// Ends the session by clearing the cookie (#20).

import { NextResponse } from "next/server";
import { SESSION_COOKIE, sessionCookieOptions } from "@/lib/session";

export async function POST(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), {
    // 303 so the browser follows with GET rather than replaying the POST.
    status: 303,
  });
  response.cookies.set(SESSION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
  return response;
}
