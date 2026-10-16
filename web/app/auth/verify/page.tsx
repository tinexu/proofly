"use client";

// The page the sign-in email links to: /auth/verify?token=…
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { safeNext, useAuth } from "@/lib/auth";

function Verify() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const [error, setError] = useState("");
  // Links work only once; make sure we send it once even if React runs effects twice.
  const sentOnce = useRef(false);

  useEffect(() => {
    if (sentOnce.current) return;
    sentOnce.current = true;
    const token = params.get("token");
    if (!token) {
      setError("This link is missing its code. Request a new one.");
      return;
    }
    // Remove the token from the address bar and history right away.
    window.history.replaceState(null, "", "/auth/verify");
    (async () => {
      try {
        await api.verify(token);
        await refresh();
        let next: string | null = null;
        try { next = sessionStorage.getItem("proofly.next"); sessionStorage.removeItem("proofly.next"); } catch { /* optional */ }
        router.replace(safeNext(next));
      } catch (err) {
        setError(err instanceof Error ? err.message : "This sign-in link didn't work.");
      }
    })();
  }, [params, refresh, router]);

  if (error)
    return (
      <div className="stack">
        <h1>That link didn&apos;t work</h1>
        <p role="alert">{error}</p>
        <div className="row"><Link className="button" href="/signin">Get a new link</Link></div>
      </div>
    );
  return <p className="muted" role="status">Signing you in…</p>;
}

export default function VerifyPage() {
  return <Suspense fallback={<p className="muted">Signing you in…</p>}><Verify /></Suspense>;
}