"use client";

// S6 / Decision summary: next steps, what is NOT verified, export (F06), report, delete (F07).
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CLAIM_TYPES, type Case, type Decision } from "@/lib/types";
import { CLAIM_CONTENT, DECISION_LABEL, FACT_LABEL } from "@/lib/content";
import { findDiscrepancies, paymentFlags, unknowns } from "@/lib/rules";
import { api } from "@/lib/api";
import { CaseShell, Notice, type CaseContext } from "@/components/ui";

function SummaryPanel({ kase, ctx }: { kase: Case; ctx: CaseContext }) {
  const router = useRouter();
  const [decision, setDecision] = useState<Decision | undefined>(kase.decision);
  const [note, setNote] = useState(kase.decisionNote ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const missing = unknowns(kase);
  const disc = findDiscrepancies(kase);
  const flags = paymentFlags(kase.offer);
  const nextChecks = CLAIM_TYPES.filter((t) => kase.claims[t].state !== "SUPPORTED").map((t) => CLAIM_CONTENT[t].independentChecks[0]);

  async function saveDecision() {
    if (!decision) return;
    setError("");
    setBusy(true);
    try {
      await ctx.update(await api.setDecision(kase.id, decision, note.trim()));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the decision.");
    } finally {
      setBusy(false);
    }
  }

  async function exportSummary(includeNotes: boolean) {
    setError("");
    setBusy(true);
    try {
      const { blob, filename } = await api.exportCase(kase.id, includeNotes);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      await ctx.reload(); // the download shows in the activity log
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't download the summary.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setError("");
    setBusy(true);
    try {
      await api.deleteCase(kase.id);
      router.push("/cases");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete the case.");
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card stack">
        <h2>What has NOT been verified</h2>
        <ul>{missing.map((m) => <li key={m}>{m}</li>)}</ul>
        {(disc.length > 0 || flags.length > 0) && (
          <Notice tone="caution" title="Open issues">
            <ul>
              {disc.map((d) => <li key={d.field}>{FACT_LABEL[d.field]}: a file says something different from the listing.</li>)}
              {flags.map((f) => <li key={f.message}>{f.message}</li>)}
            </ul>
          </Notice>
        )}
      </section>

      <section className="card stack">
        <h2>Next steps</h2>
        <ol>
          {nextChecks.map((c) => <li key={c}>{c}</li>)}
          <li>Verify using independent contact info before paying.</li>
        </ol>
      </section>

      <section className="card stack">
        <h2>Your decision</h2>
        <fieldset className="stack">
          <legend className="sr-only">Decision</legend>
          {(Object.keys(DECISION_LABEL) as Decision[]).map((d) => (
            <label key={d} className="check">
              <input type="radio" name="decision" checked={decision === d} onChange={() => { setDecision(d); setSaved(false); }} />
              <span>{DECISION_LABEL[d]}</span>
            </label>
          ))}
        </fieldset>
        <label htmlFor="note">Note to yourself (optional)</label>
        <textarea id="note" rows={2} maxLength={1000} value={note} onChange={(e) => { setNote(e.target.value); setSaved(false); }} />
        <div className="row">
          <button className="button" onClick={saveDecision} disabled={!decision || busy}>{busy ? "Saving…" : "Save decision"}</button>
        </div>
        {saved && <p className="small" role="status">Saved.</p>}
        {error && <p className="error small" role="alert">{error}</p>}
      </section>

      <section className="card stack">
        <h2>Download a summary</h2>
        <p className="small">
          A text file (Markdown) of everything recorded in this case: the offer, each claim and who set it, listing vs.
          files, file fingerprints, what has NOT been verified, your decision and the activity log.
        </p>
        <div className="row">
          <button className="button secondary" onClick={() => void exportSummary(true)} disabled={busy}>Download summary</button>
          <button className="button ghost" onClick={() => void exportSummary(false)} disabled={busy}>Download a copy to share</button>
        </div>
        <p className="small muted">The copy to share leaves out your notes, the subletter&apos;s contact details and the listing link.</p>
      </section>

      <section className="card stack">
        <h2>Report a suspicious listing</h2>
        <p className="small">
          If something seems wrong, report the post to the platform where you found it. You can also report rental
          scams to the FTC at <a href="https://reportfraud.ftc.gov" target="_blank" rel="noreferrer">ReportFraud.ftc.gov</a>.
        </p>
      </section>

      <section className="card stack danger-zone">
        <h2>Delete this case</h2>
        <p className="small">Your case disappears right away and its personal details (address, link, contact, notes) are wiped at once. Everything left is permanently removed within 24 hours.</p>
        {!confirmDelete ? (
          <div className="row"><button className="button ghost" onClick={() => setConfirmDelete(true)}>Delete case</button></div>
        ) : (
          <div className="row">
            <button className="button danger" onClick={remove} disabled={busy}>Yes, delete permanently</button>
            <button className="button ghost" onClick={() => setConfirmDelete(false)}>Cancel</button>
          </div>
        )}
      </section>
    </>
  );
}

export default function SummaryPage() {
  return <CaseShell>{(kase, ctx) => <SummaryPanel kase={kase} ctx={ctx} />}</CaseShell>;
}