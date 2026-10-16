"use client";

// S3 / Case dashboard: claim-based checklist with source attribution (F02).
import Link from "next/link";
import { CLAIM_TYPES } from "@/lib/types";
import { CLAIM_CONTENT } from "@/lib/content";
import { findDiscrepancies, paymentFlags, progress } from "@/lib/rules";
import { CaseShell, ClaimCard, Notice, formatWhen } from "@/components/ui";

export default function CaseDashboard() {
  return (
    <CaseShell>
      {(kase) => {
        const p = progress(kase);
        const disc = findDiscrepancies(kase);
        const flags = paymentFlags(kase.offer);
        const next = CLAIM_TYPES.find((t) => kase.claims[t].state !== "SUPPORTED");
        return (
          <>
            <section className="summary-strip" aria-label="Checklist status">
              <div><span className="num">{p.supported}</span> supported</div>
              <div><span className="num">{p.unresolved}</span> not confirmed</div>
              <div><span className="num">{p.conflicting}</span> conflicting</div>
            </section>

            {(disc.length > 0 || flags.length > 0) && (
              <Notice tone="caution" title="Things to look at before going further">
                <ul>
                  {disc.length > 0 && <li>{disc.length} detail{disc.length > 1 ? "s" : ""} don't match the listing. <Link href={`/case/${kase.id}/review`}>Compare them</Link>.</li>}
                  {flags.map((f) => <li key={f.message}>{f.message}</li>)}
                </ul>
              </Notice>
            )}

            {next && (
              <Notice title="Suggested next check">
                <p>{CLAIM_CONTENT[next].question}</p>
                <p className="small">{CLAIM_CONTENT[next].independentChecks[0]}</p>
                <p className="small"><Link href={`/case/${kase.id}/request`}>Ask the subletter for evidence</Link> or <Link href={`/case/${kase.id}/review`}>see how to check independently</Link>.</p>
              </Notice>
            )}

            <section className="stack" aria-label="Claims">
              <h2>Claims</h2>
              {CLAIM_TYPES.map((t) => <ClaimCard key={t} kase={kase} claim={kase.claims[t]} />)}
            </section>

            <details className="card">
              <summary>Activity log ({kase.events.length})</summary>
              <ol className="log">
                {[...kase.events].reverse().map((e) => (
                  <li key={e.id}><span className="muted small">{formatWhen(e.at)} · {e.actor}</span> {e.action}</li>
                ))}
              </ol>
            </details>
          </>
        );
      }}
    </CaseShell>
  );
}