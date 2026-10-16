"use client";

// S4 / Request evidence. Evidence requests (scoped, expiring, revocable links)
// arrive with the evidence backend in Week 6; until then this page says so plainly.
import Link from "next/link";
import { CLAIM_TYPES } from "@/lib/types";
import { CLAIM_CONTENT } from "@/lib/content";
import { CaseShell, Notice } from "@/components/ui";

export default function RequestPage() {
  return (
    <CaseShell>
      {(kase) => (
        <>
          <Notice title="Evidence requests aren't available yet">
            <p>Soon you&apos;ll be able to send the subletter a private, expiring link asking for exactly the items below. Until then, ask them directly and check what you can yourself.</p>
          </Notice>
          <section className="stack">
            <h2>What you can ask for</h2>
            {CLAIM_TYPES.filter((t) => kase.claims[t].state !== "SUPPORTED").map((t) => (
              <article key={t} className="card stack">
                <strong>{CLAIM_CONTENT[t].label}</strong>
                <p className="small">Ask for: {CLAIM_CONTENT[t].requestPrompt}</p>
                <p className="small muted">Check yourself: {CLAIM_CONTENT[t].independentChecks[0]}</p>
              </article>
            ))}
          </section>
          <p className="small">When you&apos;ve checked something, <Link href={`/case/${kase.id}/review`}>record your review</Link>.</p>
        </>
      )}
    </CaseShell>
  );
}