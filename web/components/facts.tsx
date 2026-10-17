"use client";

// S5 / Compare: the renter notes what a file says, the API compares it with the listing
// (Week 7, Day 3; spec F05). Proofly never reads files itself.
import { useState } from "react";
import { FACT_FIELDS, type Case, type FactField } from "@/lib/types";
import { CLAIM_CONTENT, FACT_CLAIM, FACT_LABEL } from "@/lib/content";
import { api } from "@/lib/api";
import { DATE_FACTS as DATES, MONEY_FACTS as MONEY, formatFact } from "@/lib/rules";
import type { CaseContext } from "./ui";

const RESULT_LABEL = {
  matches: "Matches the listing",
  differs: "Differs from the listing",
  listing_silent: "The listing didn't say",
} as const;

function FactRow({ kase, field, ctx }: { kase: Case; field: FactField; ctx: CaseContext }) {
  const fact = kase.providedFacts[field];
  const claim = FACT_CLAIM[field];
  // Clean files only, the ones sent for this detail's claim first.
  const files = kase.evidence
    .filter((e) => e.scanStatus === "clean")
    .sort((a, b) => Number(b.claimTypes.includes(claim)) - Number(a.claimTypes.includes(claim)));
  const file = fact ? kase.evidence.find((e) => e.id === fact.evidenceId) : undefined;

  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(fact?.value ?? "");
  const [fileId, setFileId] = useState(fact?.evidenceId ?? files[0]?.id ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setError("");
    setBusy(true);
    try {
      await action();
      await ctx.reload(); // the claim's state may have changed too
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (!value.trim()) return setError("Enter what the file says.");
    if (!fileId) return setError("Choose the file it comes from.");
    void run(() => api.putFact(kase.id, field, value.trim(), fileId));
  }

  const id = `fact-${field}`;
  return (
    <div className={`fact-row${fact?.result === "differs" ? " fact-differs" : ""}`}>
      <div className="fact-head">
        <strong>{FACT_LABEL[field]}</strong>
        {fact && (
          <span className={`fact-result fact-${fact.result}`}>
            <span aria-hidden="true">{fact.result === "differs" ? "▲ " : fact.result === "matches" ? "= " : "? "}</span>
            {RESULT_LABEL[fact.result]}
          </span>
        )}
      </div>
      <div className="compare small">
        <div><span className="muted block">Listing says</span>{formatFact(field, kase.offer[field])}</div>
        <div>
          <span className="muted block">A file says</span>
          {fact ? <>{formatFact(field, fact.value)} <span className="muted">({file?.fileName ?? "file"})</span></> : <span className="muted">Not noted</span>}
        </div>
      </div>

      {!editing ? (
        <div className="row">
          <button className="button ghost small-button" onClick={() => { setEditing(true); setValue(fact?.value ?? ""); }} disabled={!files.length}>
            {fact ? "Change" : "Note what a file says"}
          </button>
          {fact && <button className="button ghost small-button" disabled={busy} onClick={() => void run(() => api.removeFact(kase.id, field))}>Remove</button>}
        </div>
      ) : (
        <div className="stack fact-form">
          <label htmlFor={id}>What does the file say? ({FACT_LABEL[field].toLowerCase()})</label>
          {DATES.includes(field) ? (
            <input id={id} type="date" value={value} onChange={(e) => setValue(e.target.value)} />
          ) : (
            <input
              id={id}
              inputMode={MONEY.includes(field) ? "decimal" : undefined}
              maxLength={200}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={MONEY.includes(field) ? "e.g. 950" : field === "address" ? "As written in the file" : "e.g. Check to the property office"}
            />
          )}
          <label htmlFor={`${id}-file`}>From which file?</label>
          <select id={`${id}-file`} value={fileId} onChange={(e) => setFileId(e.target.value)}>
            {files.map((e) => (
              <option key={e.id} value={e.id}>
                {e.fileName}{e.claimTypes.includes(claim) ? "" : ` (sent for "${CLAIM_CONTENT[e.claimTypes[0]].label}")`}
              </option>
            ))}
          </select>
          {error && <p className="error small" role="alert">{error}</p>}
          <div className="row">
            <button className="button secondary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button className="button ghost" onClick={() => { setEditing(false); setError(""); }} disabled={busy}>Cancel</button>
          </div>
        </div>
      )}
      {!editing && error && <p className="error small" role="alert">{error}</p>}
    </div>
  );
}

export function FactsPanel({ kase, ctx }: { kase: Case; ctx: CaseContext }) {
  const hasClean = kase.evidence.some((e) => e.scanStatus === "clean");
  const differs = FACT_FIELDS.filter((f) => kase.providedFacts[f]?.result === "differs");
  return (
    <section className="stack" aria-labelledby="mismatches">
      <h2 id="mismatches">Listing vs. files</h2>
      {!hasClean ? (
        <p className="muted">
          No file has passed the virus check yet, so there&apos;s nothing to compare. That doesn&apos;t mean everything checks out.
        </p>
      ) : (
        <p className="muted">
          Proofly doesn&apos;t read files. Open a file, then note what it says about the details below. Proofly compares
          each one with the listing, and a difference marks that claim conflicting.
        </p>
      )}
      {differs.length > 0 && (
        <p className="small" role="status">
          <strong>{differs.length} detail{differs.length > 1 ? "s differ" : " differs"} from the listing.</strong>{" "}
          Ask the subletter why, and check with the landlord or property manager using contact details you found yourself.
        </p>
      )}
      <div className="card stack">
        {FACT_FIELDS.map((f) => <FactRow key={f} kase={kase} field={f} ctx={ctx} />)}
      </div>
    </section>
  );
}