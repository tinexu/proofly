"use client";

// S5 / Compare & review: claimed vs provided, manual assessment with provenance
// (saved to the API), and how to check independently.
// Mismatch handling returns in Week 7, once evidence (Week 6) can disagree with the listing.
import { useState } from "react";
import { CLAIM_TYPES, type Case, type ClaimType, type EvidenceKind } from "@/lib/types";
import { CLAIM_CONTENT, EVIDENCE_KIND_LABEL, SIGNALS } from "@/lib/content";
import { assertedFor, evidenceFor } from "@/lib/rules";
import { api, type ReviewState } from "@/lib/api";
import { CaseShell, Notice, StatusBadge, formatWhen, type CaseContext } from "@/components/ui";

function AssessClaim({ kase, type, ctx }: { kase: Case; type: ClaimType; ctx: CaseContext }) {
  const claim = kase.claims[type];
  const [state, setState] = useState<ReviewState>(claim.state === "CONFLICTING" ? "CONFLICTING" : "REVIEW_NEEDED");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<Parameters<CaseContext["update"]>[0]>) {
    setError("");
    setBusy(true);
    try {
      await ctx.update(await action());
      setRationale("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (!rationale.trim()) {
      setError("Add a short note on why, so the decision has a record.");
      return;
    }
    void run(() => api.reviewClaim(kase.id, type, state, rationale.trim()));
  }

  return (
    <details className="assess">
      <summary>Record your review</summary>
      <div className="stack">
        {claim.reviewer === "user" && claim.rationale && (
          <p className="small">Your note ({formatWhen(claim.updatedAt)}): {claim.rationale}</p>
        )}
        <label htmlFor={`state-${type}`}>Your assessment</label>
        <select id={`state-${type}`} value={state} onChange={(e) => setState(e.target.value as ReviewState)}>
          <option value="REVIEW_NEEDED">Still not confirmed</option>
          <option value="CONFLICTING">Conflicting</option>
        </select>
        <p className="small muted">&quot;Supported&quot; always has to name the evidence behind it. That becomes possible once evidence can be added.</p>
        <label htmlFor={`why-${type}`}>Why? (saved with this claim, not shared)</label>
        <textarea id={`why-${type}`} rows={2} maxLength={1000} value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="e.g. The landlord's office hasn't replied yet." />
        {error && <p className="error small" role="alert">{error}</p>}
        <div className="row">
          <button className="button secondary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save review"}</button>
          {claim.reviewer === "user" && (
            <button className="button ghost" disabled={busy} onClick={() => void run(() => api.clearReview(kase.id, type))}>Undo my review</button>
          )}
        </div>
      </div>
    </details>
  );
}

function ReviewPanel({ kase, ctx }: { kase: Case; ctx: CaseContext }) {
  return (
    <>
      <section className="stack">
        <h2>Mismatches</h2>
        <p className="muted">No evidence has been received, so there&apos;s nothing to compare yet. That doesn&apos;t mean everything checks out.</p>
      </section>

      <section className="stack">
        <h2>Claim by claim</h2>
        {CLAIM_TYPES.map((t) => {
          const ev = evidenceFor(kase, t);
          return (
            <article key={t} className="card stack">
              <div className="claim-head"><h3>{CLAIM_CONTENT[t].label}</h3><StatusBadge state={kase.claims[t].state} /></div>
              <div className="compare">
                <div><span className="muted small block">Claimed</span>{assertedFor(t, kase.offer)}</div>
                <div><span className="muted small block">Provided</span>{ev.length ? ev.map((e) => EVIDENCE_KIND_LABEL[e.kind]).join(", ") : "Nothing yet"}</div>
              </div>
              <div>
                <strong className="small">How to check independently</strong>
                <ul className="small">{CLAIM_CONTENT[t].independentChecks.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
              <AssessClaim kase={kase} type={t} ctx={ctx} />
            </article>
          );
        })}
      </section>

      <section className="stack">
        <h2>What each kind of evidence can and can&apos;t show</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th scope="col">Evidence</th><th scope="col">Supports</th><th scope="col">Does NOT prove</th></tr></thead>
            <tbody>
              {(Object.keys(SIGNALS) as EvidenceKind[]).map((k) => (
                <tr key={k}><th scope="row">{EVIDENCE_KIND_LABEL[k]}</th><td>{SIGNALS[k].supports}</td><td>{SIGNALS[k].doesNotProve}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <Notice>Contact details the subletter gives you can be faked. Look up the landlord or manager yourself.</Notice>
      </section>
    </>
  );
}

export default function ReviewPage() {
  return <CaseShell>{(kase, ctx) => <ReviewPanel kase={kase} ctx={ctx} />}</CaseShell>;
}