"use client";

// Sign in with an email link; API emails a one-time link;
// in development it prints in the terminal running the API.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { safeNext, useAuth } from "@/lib/auth";

function SignInForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const next = safeNext(params.get("next"));
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      // Remember where to return after the link is used (same browser only).
      try { sessionStorage.setItem("proofly.next", next); } catch { /* optional */ }
      await api.requestLink(email.trim());
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <div className="stack">
        <h1>Check your email</h1>
        <p className="lead">If <strong>{email.trim()}</strong> can receive email, a sign-in link is on its way. It works once and expires in 15 minutes.</p>
        <div className="notice"><strong>Developing locally?</strong><div>The email prints in the terminal running the API. Open the link from there in this browser.</div></div>
        <div className="row"><button className="button ghost" onClick={() => setSent(false)}>Use a different email</button></div>
      </div>
    );

  return (
    <form className="stack" onSubmit={onSubmit} noValidate>
      <div>
        <h1>Sign in</h1>
        <p className="lead">We&apos;ll email you a link. No password needed.</p>
      </div>
      <div className="card stack">
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@school.edu" aria-describedby={error ? "email-error" : undefined} aria-invalid={!!error} />
        {error && <p id="email-error" className="error small" role="alert">{error}</p>}
        <div className="row"><button className="button" type="submit" disabled={busy || !email.trim()}>{busy ? "Sending…" : "Email me a link"}</button></div>
      </div>
    </form>
  );
}

export default function SignInPage() {
  return <Suspense fallback={<p className="muted">Loading…</p>}><SignInForm /></Suspense>;
}