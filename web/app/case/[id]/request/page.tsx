"use client";

// S4 / Request evidence (Week 6, Day 5): scoped, expiring, revocable links (F03).
// The link is shown once, right after it's created. Proofly keeps only a hash of it.
import { useState } from "react";
import { CLAIM_TYPES, type Case, type ClaimType } from "@/lib/types";
import { CLAIM_CONTENT } from "@/lib/content";
import { requestStatus } from "@/lib/rules";
import { api, type ApiRequestCreated } from "@/lib/api";
import { CaseShell, FileLine, Notice, formatWhen, type CaseContext } from "@/components/ui";

const EXPIRY_OPTIONS = [
  { hours: 24, label: "24 hours" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "7 days" },
];

const STATUS_TEXT = { open: "Waiting for a reply", responded: "Replied", expired: "Expired", revoked: "Revoked" };

function NewLink({ created, onDone }: { created: ApiRequestCreated; onDone: () => void }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(created.link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="card stack link-once" aria-live="polite">
      <h2>Your link is ready</h2>
      <p className="small"><strong>Copy it now.</strong> For privacy, Proofly can&apos;t show this link again. If you lose it, revoke it and make a new one.</p>
      <div className="linkbox"><code>{created.link}</code></div>
      <div className="row">
        <button className="button" onClick={copy}>{copied ? "Copied" : "Copy link"}</button>
        <a className="button secondary" href={created.link} target="_blank" rel="noopener noreferrer">Preview what they see</a>
        <button className="button ghost" onClick={onDone}>Done</button>
      </div>
      <p className="muted small">Send it to the subletter in the chat you already use with them. It expires {formatWhen(created.expires_at)}.</p>
    </section>
  );
}

function RequestPanel({ kase, ctx }: { kase: Case; ctx: CaseContext }) {
  const defaultScopes = CLAIM_TYPES.filter((t) => t !== "property_existence" && kase.claims[t].state !== "SUPPORTED");
  const [scopes, setScopes] = useState<ClaimType[]>(defaultScopes);
  const [hours, setHours] = useState(72);
  const [created, setCreated] = useState<ApiRequestCreated | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const toggle = (t: ClaimType) => setScopes((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  async function create() {
    if (!scopes.length) return;
    setError("");
    setBusy(true);
    try {
      setCreated(await api.createRequest(kase.id, scopes, hours));
      await ctx.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create the link.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(requestId: string) {
    setError("");
    try {
      await api.revokeRequest(kase.id, requestId);
      if (created?.id === requestId) setCreated(null);
      await ctx.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't revoke the link.");
    }
  }

  return (
    <>
      {created && <NewLink created={created} onDone={() => setCreated(null)} />}

      <section className="card stack">
        <h2>Ask the subletter for evidence</h2>
        <p className="small">
          You&apos;ll get a private link to send them. They&apos;ll see only what you ask for here, nothing about you.
          They choose what to share, and the link works for one reply.
        </p>
        <fieldset className="stack">
          <legend>What to ask for</legend>
          {CLAIM_TYPES.map((t) => (
            <label key={t} className="check">
              <input type="checkbox" checked={scopes.includes(t)} onChange={() => toggle(t)} />
              <span>
                <strong>{CLAIM_CONTENT[t].label}</strong>
                <span className="muted small block">They&apos;ll be asked: {CLAIM_CONTENT[t].requestPrompt}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label htmlFor="expiry">Link expires after</label>
        <select id="expiry" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          {EXPIRY_OPTIONS.map((o) => <option key={o.hours} value={o.hours}>{o.label}</option>)}
        </select>
        {error && <p className="error small" role="alert">{error}</p>}
        <div className="row">
          <button className="button" onClick={create} disabled={!scopes.length || busy}>{busy ? "Creating…" : "Create request link"}</button>
        </div>
        <p className="muted small">Uploads are limited to PDFs and photos and are checked for viruses before you can open them. We never ask for a Social Security number, bank logins, or a full ID.</p>
      </section>

      <section className="stack">
        <h2>Your links</h2>
        {kase.requests.length === 0 && <p className="muted">No links yet.</p>}
        {kase.requests.map((r) => {
          const status = requestStatus(r);
          const files = kase.evidence.filter((e) => e.requestId === r.id);
          return (
            <article key={r.id} className="card stack">
              <div className="claim-head">
                <span className={`status-pill status-${status}`}>{STATUS_TEXT[status]}</span>
                <span className="muted small">Created {formatWhen(r.createdAt)} · {status === "open" ? "expires" : "expired"} {formatWhen(r.expiresAt)}</span>
              </div>
              <p className="small">Asks for: {r.scopes.map((s) => CLAIM_CONTENT[s].label).join("; ")}</p>
              {status === "responded" && files.length > 0 && (
                <ul className="evidence-list">{files.map((e) => <li key={e.id}><FileLine e={e} /></li>)}</ul>
              )}
              {status === "open" && (
                <div className="row"><button className="button ghost" onClick={() => revoke(r.id)}>Revoke link</button></div>
              )}
            </article>
          );
        })}
      </section>

      {kase.evidence.some((e) => e.scanStatus === "pending_scan") && (
        <Notice title="Some files are still being checked">
          <p className="small">Files unlock once they pass the virus check. Reload this page in a minute.</p>
        </Notice>
      )}
    </>
  );
}

export default function RequestPage() {
  return <CaseShell>{(kase, ctx) => <RequestPanel kase={kase} ctx={ctx} />}</CaseShell>;
}