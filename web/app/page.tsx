"use client";

// S1 / Start
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function StartPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) {
      try {
        const parsed = new URL(trimmed);
        if (!/^https?:$/.test(parsed.protocol)) throw new Error();
      } catch {
        setError("That doesn't look like a web link. You can also enter the details yourself.");
        return;
      }
    }
    router.push(trimmed ? `/case/new?url=${encodeURIComponent(trimmed)}` : "/case/new");
  }

  return (
    <div className="stack hero">
      <h1>Check a sublet before you pay.</h1>
      <p className="lead">
        Found a sublet on Facebook, Reddit, Discord or a group chat? Proofly helps you see what evidence you have,
        what's missing, and what to check next, before you send a deposit.
      </p>

      <form className="card stack" onSubmit={onSubmit} noValidate>
        <label htmlFor="url">Paste the listing link (optional)</label>
        <input
          id="url"
          type="url"
          inputMode="url"
          placeholder="https://www.facebook.com/groups/…"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setError(""); }}
          aria-describedby={error ? "url-error" : "privacy"}
          aria-invalid={!!error}
        />
        {error && <p id="url-error" className="error small">{error}</p>}
        <div className="row">
          <button type="submit" className="button">{url.trim() ? "Continue with this link" : "Enter details manually"}</button>
        </div>
        <p id="privacy" className="muted small">
          We only use what you type here. We don't read your messages or log into your accounts. Don't paste other
          people's private details. You'll be asked to sign in by email so you can come back to your case.
        </p>
      </form>

      {user && (
        <div className="card subtle stack">
          <strong>Welcome back</strong>
          <p className="small">Pick up where you left off.</p>
          <div className="row"><Link className="button secondary" href="/cases">My cases</Link></div>
        </div>
      )}

      <section className="stack">
        <h2>What Proofly does and doesn't do</h2>
        <ul className="plain">
          <li>Shows each claim with the evidence behind it, and what's still unknown.</li>
          <li>Helps you request limited evidence from the subletter through an expiring link.</li>
          <li>Points you to checks you can do yourself, like contacting the landlord directly.</li>
          <li><strong>Does not</strong> declare a listing trustworthy, hold your money, or give legal advice.</li>
        </ul>
      </section>
    </div>
  );
}