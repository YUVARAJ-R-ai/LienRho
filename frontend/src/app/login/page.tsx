"use client";

// Sign-in screen (#20).
//
// A client component because it owns form state and an error message. It posts
// to the /api/auth/login route handler rather than to FastAPI directly, so the
// access token is set as an httpOnly cookie and never reaches this code.

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      setError("Incorrect email or password.");
      setSubmitting(false);
      return;
    }

    // refresh() so the server components re-render with the new cookie —
    // push() alone can serve them from the client router cache, still
    // unauthenticated.
    router.replace(searchParams.get("next") ?? "/");
    router.refresh();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
    >
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          LIENRHO
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Sign in to your organisation&apos;s action queue.
        </p>
      </div>

      <label className="block text-sm font-medium text-slate-700" htmlFor="email">
        Email
      </label>
      <input
        id="email"
        type="email"
        autoComplete="username"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="mt-1 mb-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-900"
      />

      <label className="block text-sm font-medium text-slate-700" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-900"
      />

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="mt-6 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-60"
      >
        {submitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-6">
      {/* useSearchParams needs a Suspense boundary to keep the route from
          opting the whole page out of prerendering. */}
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
