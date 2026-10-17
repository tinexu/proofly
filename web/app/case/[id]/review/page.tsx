"use client";

// S5 / Compare & review: claimed vs provided, manual assessment with provenance
// (saved to the API), and how to check independently.
// Week 7, Day 2: "Supported" names a clean file and says what in it supports the claim.
// Week 7, Day 3: "Listing vs. files" (components/facts.tsx) compares what files say with the listing.
import { useState } from "react";
import { CLAIM_TYPES, type Case, type ClaimType, type EvidenceKind } from "@/lib/types";
import { CLAIM_CONTENT, EVIDENCE_KIND_LABEL, SIGNALS } from "@/lib/content";
import { assertedFor, evidenceFor } from "@/lib/rules";
import { api, type ReviewState } from "@/lib/api";
import { CaseShell, FileLine, Notice, StatusBadge, formatWhen, type CaseContext } from "@/components/ui";
import { FactsPanel } from "@/components/facts";

function AssessClaim({ kase, type, ctx }: { kase: Case; type: ClaimType; ctx: CaseContext }) {
  const claim = kase.claims[type];
  // Files that can back a "supported" review: clean ones from this case, this claim's own first.
  const usable = kase.evidence
    .filter((e) => e.scanStatus === "clean")
    .sort((a, b) => Number(b.claimTypes.includes(type)) - Number(a.claimTypes.includes(type)));
  const initial: ReviewState = claim.state === "SUPPORTED" || claim.state === "CONFLICTING" ? claim.state : "REVIEW_NEEDED";
  const [state, setState] = useState<ReviewState>(initial);
  const [fileId, setFileId] = useState(claim.supportedBy ?? usable[0]?.id ?? "");
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
    if (state === "SUPPORTED" && !fileId) {
      setError("Choose the file this is based on.");
      return;
    }
    if (!rationale.trim()) {
      setError(state === "SUPPORTED"
        ? "Say what in the file supports this, e.g. which page or line."
        : "Add a short note on why, so the decision has a record.");
      return;
    }
    void run(() => api.reviewClaim(kase.id, type, state, rationale.trim(), state === "SUPPORTED" ? fileId : undefined));
  }

  const placeholder = state === "SUPPORTED"
    ? "e.g. Page 3 of the lease names this person as a tenant of this unit."
    : "e.g. The landlord's office hasn't replied yet.";

  return (
    <details className="assess">
      <summary>Record your review</summary>
      <div className="stack">
        {claim.reviewer === "user" && claim.rationale && (
          <p className="small">Your note ({formatWhen(claim.updatedAt)}): {claim.rationale}</p>
        )}
        <label htmlFor={`state-${type}`}>Your assessment</label>
        <select id={`state-${type}`} value={state} onChange={(e) => { setState(e.target.value as ReviewState); setError(""); }}>
          <option value="REVIEW_NEEDED">Still not confirmed</option>
          <option value="SUPPORTED" disabled={usable.length === 0}>
            Supported by a file{usable.length === 0 ? " (needs a file that passed the virus check)" : ""}
          </option>
          <option value="CONFLICTING">Conflicting</option>
        </select>
        {usable.length === 0 && (
          <p className="small muted">&quot;Supported&quot; always names the file behind it. Request evidence first; once a file passes the virus check you can choose it here.</p>
        )}
        {state === "SUPPORTED" && usable.length > 0 && (
          <>
            <label htmlFor={`file-${type}`}>Which file is this based on?</label>
            <select id={`file-${type}`} value={fileId} onChange={(e) => setFileId(e.target.value)}>
              {usable.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.fileName}{e.claimTypes.includes(type) ? "" : ` (sent for "${CLAIM_CONTENT[e.claimTypes[0]].label}")`}
                </option>
              ))}
            </select>
            <Notice>
              Only mark this supported if you opened the file and it shows the claim. Proofly hasn&apos;t checked the
              file, and a file can&apos;t show on its own whether it&apos;s genuine, current, or about this unit.
            </Notice>
          </>
        )}
        <label htmlFor={`why-${type}`}>{state === "SUPPORTED" ? "What in the file supports it?" : "Why?"} (saved with this claim, not shared)</label>
        <textarea id={`why-${type}`} rows={2} maxLength={1000} value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder={placeholder} />
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
      <FactsPanel kase={kase} ctx={ctx} />

      <section className="stack">
        <h2>Claim by claim</h2>
        {CLAIM_TYPES.map((t) => {
          const ev = evidenceFor(kase, t);
          return (
            <article key={t} className="card stack">
              <div className="claim-head"><h3>{CLAIM_CONTENT[t].label}</h3><StatusBadge state={kase.claims[t].state} /></div>
              <div className="compare">
                <div><span className="muted small block">Claimed</span>{assertedFor(t, kase.offer)}</div>
                <div>
                  <span className="muted small block">Provided</span>
                  {ev.length ? ev.map((e) => (e.scanStatus ? <FileLine key={e.id} e={e} /> : <span key={e.id} className="block">{EVIDENCE_KIND_LABEL[e.kind]}</span>)) : "Nothing yet"}
                </div>
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