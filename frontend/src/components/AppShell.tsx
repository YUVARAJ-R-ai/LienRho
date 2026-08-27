"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Action Queue" },
  { href: "/forecast", label: "Cash Forecast" },
  { href: "/approvals", label: "Approvals" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // The sign-in screen is outside the app: showing nav to somebody who has no
  // session would offer links that only bounce them back here (#20).
  if (pathname === "/login") {
    return <div className="min-h-screen bg-slate-50">{children}</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-baseline gap-2">
            <span className="text-lg font-semibold tracking-tight text-slate-900">
              LIENRHO
            </span>
            <span className="hidden text-xs text-slate-500 sm:inline">
              When invoices wait, cash shouldn&apos;t.
            </span>
          </Link>
          <nav className="flex gap-1">
            {navItems.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          {/* A plain form POST, not a fetch — clearing an httpOnly cookie has
              to happen in a route handler, and this needs no JavaScript. */}
          <form action="/api/auth/logout" method="post">
            <button
              type="submit"
              className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
