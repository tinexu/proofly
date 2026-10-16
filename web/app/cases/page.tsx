"use client";

// My cases
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApiCaseSummary } from "@/lib/api";
import { RequireAuth } from "@/lib/auth";
import { formatWhen } from "@/components/ui";

function CaseList() {
  const [cases, setCases] = useState<ApiCaseSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listCases().then(setCases).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="stack">
      <div className="claim-head">
        <h1>My cases</h1>
        <Link className="button" href="/case/new">Check a new sublet</Link>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {cases === null && !error && <p className="muted">Loading…</p>}
      {cases?.length === 0 && <p className="muted">No cases yet. Start by entering an offer you found.</p>}
      {cases && cases.length > 0 && (
        <ul className="plain stack">
          {cases.map((c) => (
            <li key={c.id}>
              <Link href={`/case/${c.id}`} className="card case-link">
                <strong>{c.address}</strong>
                <span className="muted small block">Started {formatWhen(c.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CasesPage() {
  return <RequireAuth><CaseList /></RequireAuth>;
}