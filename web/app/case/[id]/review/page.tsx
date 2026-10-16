"use client";

// S5 / Compare & review: claimed vs provided, mismatches as separate items (F05),
// manual assessment with provenance, and how to check independently.
import { useState } from "react";
import { CLAIM_TYPES, type Case, type ClaimState, type ClaimType, type EvidenceKind } from "@/lib/types";
import { CLAIM_CONTENT, EVIDENCE_KIND_LABEL, EVIDENCE_SOURCE_LABEL, FACT_LABEL, SIGNALS } from "@/lib/content";
import { assertedFor, evidenceFor, findDiscrepancies, type Discrepancy } from "@/lib/rules";
import { useStore } from "@/lib/store";
import { CaseShell, Notice, StatusBadge } from "@/components/ui";

function DiscrepancyItem({ kase, d }: { kase: Case; d: Discrepancy }) {
  const { updateCase } = useStore();
  const label = FACT_LABEL[d.field];
  return (
    <li className="card stack">
      <strong>{label} doesn't match</strong>
      <div className="compare">
        <div><span className="muted small block">Listing or your entry</span>{d.listed || "(blank)"}</div>
        <div><span className="muted small block">Evidence says</span>{d.provided}</div>
      </div>
      <p className="small">Ask the subletter which is correct, in writing, and confirm with the landlord or property manager.</p>
      <div className="row">
        <button className="button secondary" onClick={() => updateCase(kase.id, (c) => ({ ...c, offer: { ...c.offer, [d.field]: d.provided } }), `Corrected ${label.toLowerCase()} to match the evidence`)}>
          My entry was wrong. Use the evidence value
        </button>
        <button className="button ghost" onClick={() => updateCase(kase.id, (c) => ({ ...c, providedFacts: { ...c.providedFacts, [d.field]: { ...c.providedFacts[d.field]!, acknowledged: true } } }), `Kept listing ${label.toLowerCase()} after review`)}>
          I've resolved this with them
        </button>
      </div>
    </li>
  );
}

function AssessClaim({ kase, type }: { kase: Case; type: ClaimType }) {
  const { updateCase } = useStore();
  const claim = kase.claims[type];
  const evidence = evidenceFor(kase, type);
  const [state, setState] = useState<ClaimState>(claim.state);
  const [chosen, setChosen] = useState<string[]>(claim.evidenceIds);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");

  function save() {
    if (state === "SUPPORTED" && chosen.length === 0) {
      setError("Pick the evidence that supports this. \"Supported\" always names its evidence.");
      return;
    }
    if (!rationale.trim()) {
      setError("Add a short note on why, so the decision has a record.");
      return;
    }
    setError("");
    updateCase(kase.id, (c) => ({
      ...c,
      claims: {
        ...c.claims,
        [type]: { ...c.claims[type], state, evidenceIds: state === "SUPPORTED" ? chosen : c.claims[type].evidenceIds, rationale: rationale.trim(), reviewer: "user", updatedAt: new Date().toISOString() },
      },
    }), `Marked "${CLAIM_CONTENT[type].label}" as ${state.toLowerCase().replace("_", " ")}`);
    setRationale("");
  }

  function backToRules() {
    updateCase(kase.id, (c) => ({ ...c, claims: { ...c.claims, [type]: { ...c.claims[type], reviewer: "rules" } } }), `Cleared manual review of "${CLAIM_CONTENT[type].label}"`);
  }

  return (
    <details className="assess">
      <summary>Record your review</summary>
      <div className="stack">
        <label htmlFor={`state-${type}`}>Your assessment</label>
        <select id={`state-${type}`} value={state} onChange={(e) => setState(e.target.value as ClaimState)}>
          <option value="REVIEW_NEEDED">Still not confirmed</option>
          <option value="SUPPORTED">Supported by specific evidence</option>
          <option value="CONFLICTING">Conflicting</option>
        </select>
        {state === "SUPPORTED" && (
          evidence.length ? (
            <fieldset className="stack">
              <legend className="small">Which evidence supports it?</legend>
              {evidence.map((e) => (
                <label key={e.id} className="check">
                  <input type="checkbox" checked={chosen.includes(e.id)} onChange={() => setChosen((s) => (s.includes(e.id) ? s.filter((x) => x !== e.id) : [...s, e.id]))} />
                  <span>{EVIDENCE_KIND_LABEL[e.kind]} <span className="muted small">({EVIDENCE_SOURCE_LABEL[e.source]})</span>
                    <span className="small block">Doesn't prove: {SIGNALS[e.kind].doesNotProve}</span></span>
                </label>
              ))}
            </fieldset>
          ) : <p className="small">There's no evidence for this claim yet, so it can't be marked supported.</p>
        )}
        <label htmlFor={`why-${type}`}>Why? (kept in the activity log)</label>
        <textarea id={`why-${type}`} rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="e.g. Called the property office number from their website; they confirmed subletting is allowed." />
        {error && <p className="error small" role="alert">{error}</p>}
        <div className="row">
          <button className="button secondary" onClick={save}>Save review</button>
          {claim.reviewer === "user" && <button className="button ghost" onClick={backToRules}>Undo my review</button>}
        </div>
      </div>
    </details>
  );
}

function ReviewPanel({ kase }: { kase: Case }) {
  const disc = findDiscrepancies(kase);
  return (
    <>
      <section className="stack">
        <h2>Mismatches</h2>
        {disc.length === 0 ? (
          <p className="muted">No mismatches between the listing and the evidence received so far. That doesn't mean everything checks out; it may only mean little evidence has arrived.</p>
        ) : (
          <ul className="plain stack">{disc.map((d) => <DiscrepancyItem key={d.field} kase={kase} d={d} />)}</ul>
        )}
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
              <AssessClaim kase={kase} type={t} />
            </article>
          );
        })}
      </section>

      <section className="stack">
        <h2>What each kind of evidence can and can't show</h2>
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
  return <CaseShell>{(kase) => <ReviewPanel kase={kase} />}</CaseShell>;
}