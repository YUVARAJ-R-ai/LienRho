// Gates every screen behind a session (#20).
//
// Next 16 renamed the `middleware` convention to `proxy`; the behaviour is the
// same. This is a redirect for unauthenticated *navigation* — it is not the
// security boundary. The backend rejects any request without a valid token, so
// a user who skips this check still gets nothing; what this avoids is a screen
// that renders and then fails to fetch.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SESSION_COOKIE = "lienrho_session";

export function proxy(request: NextRequest) {
  const isLoggedIn = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  const { pathname, search } = request.nextUrl;
  const isLoginPage = pathname === "/login";

  if (!isLoggedIn && !isLoginPage) {
    const login = new URL("/login", request.url);
    // Remember where they were headed so login can return them to it.
    if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  if (isLoggedIn && isLoginPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Page navigation only.
  //
  // `/api/*` is excluded deliberately: those handlers are called by fetch, and
  // each already returns its own 401. Redirecting them would answer a JSON
  // request with a 307 to an HTML login page, which the caller would follow
  // and then fail to parse — turning "your session expired" into a parse
  // error. The negative match on _next and favicon keeps this from gating CSS
  // and JS, which would render the login page unstyled.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
