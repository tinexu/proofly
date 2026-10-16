"use client";

// S4 / Request evidence: scoped, expiring, revocable links (F03).
import Link from "next/link";
import { useEffect, useState } from "react";
import { CLAIM_TYPES, type Case, type ClaimType, type Evidence } from "@/lib/types";
import { CLAIM_CONTENT } from "@/lib/content";
import { requestStatus } from "@/lib/rules";
import { randomId } from "@/lib/ids";
import { useStore } from "@/lib/store";
import { CaseShell, Notice, formatWhen } from "@/components/ui";

const EXPIRY_OPTIONS = [
  { hours: 24, label: "24 hours" },
  { hours: 72, label: "3 days" },
  { hours: 168, label: "7 days" },
];

const STATUS_TEXT = { open: "Waiting for a reply", responded: "Replied", expired: "Expired", revoked: "Revoked" };

function RequestPanel({ kase }: { kase: Case }) {
  const { updateCase } = useStore();
  const defaultScopes = CLAIM_TYPES.filter((t) => t !== "property_existence" && kase.claims[t].state !== "SUPPORTED");
  const [scopes, setScopes] = useState<ClaimType[]>(defaultScopes);
  const [hours, setHours] = useState(72);
  const [origin, setOrigin] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => setOrigin(window.location.origin), []);

  const toggle = (t: ClaimType) => setScopes((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  function create() {
    if (!scopes.length) return;
    const now = new Date();
    const req = {
      id: randomId(8),
      token: randomId(24),
      scopes,
      createdAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + hours * 3_600_000).toISOString(),
    };
    updateCase(kase.id, (c) => ({ ...c, requests: [...c.requests, req] }), `Created an evidence request (${scopes.length} items, expires in ${hours} hours)`);
  }

  function revoke(id: string) {
    updateCase(kase.id, (c) => ({
      ...c,
      requests: c.requests.map((r) => (r.id === id ? { ...r, revokedAt: new Date().toISOString() } : r)),
    }), "Revoked an evidence request");
  }

  // Prototype-only helper so a single tester can walk the whole flow.
  function simulateReply(id: string, reqScopes: ClaimType[]) {
    const now = new Date().toISOString();
    const ev: Evidence = {
      id: randomId(8),
      kind: reqScopes.includes("person_unit_relationship") ? "lease_excerpt" : "message_screenshot",
      source: "subletter",
      description: "Simulated reply for usability testing.",
      claimTypes: reqScopes,
      addedAt: now,
      fileName: "simulated-upload.pdf",
    };
    updateCase(kase.id, (c) => ({
      ...c,
      evidence: [...c.evidence, ev],
      claims: Object.fromEntries(CLAIM_TYPES.map((t) => [t, reqScopes.includes(t) ? { ...c.claims[t], reviewer: "rules" as const } : c.claims[t]])) as Case["claims"],
      requests: c.requests.map((r) => (r.id === id ? { ...r, respondedAt: now } : r)),
    }), "Subletter uploaded evidence (simulated)", "subletter");
  }

  async function copy(link: string, id: string) {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(id);
    } catch {
      setCopied(null);
    }
  }

  return (
    <>
      <section className="card stack">
        <h2>Ask the subletter for evidence</h2>
        <p className="small">
          Send them a private link. They'll see exactly what you asked for and nothing about you except that someone
          is checking this sublet. They choose what to share.
        </p>
        <fieldset className="stack">
          <legend>What to ask for</legend>
          {CLAIM_TYPES.map((t) => (
            <label key={t} className="check">
              <input type="checkbox" checked={scopes.includes(t)} onChange={() => toggle(t)} />
              <span>
                <strong>{CLAIM_CONTENT[t].label}</strong>
                <span className="muted small block">They'll be asked: {CLAIM_CONTENT[t].requestPrompt}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label htmlFor="expiry">Link expires after</label>
        <select id="expiry" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          {EXPIRY_OPTIONS.map((o) => <option key={o.hours} value={o.hours}>{o.label}</option>)}
        </select>
        <div className="row">
          <button className="button" onClick={create} disabled={!scopes.length}>Create request link</button>
        </div>
        <p className="muted small">We never ask them for a Social Security number, bank logins, or a full ID document.</p>
      </section>

      <section className="stack">
        <h2>Your requests</h2>
        {kase.requests.length === 0 && <p className="muted">No requests yet.</p>}
        {[...kase.requests].reverse().map((r) => {
          const status = requestStatus(r);
          const link = `${origin}/r/${r.token}`;
          return (
            <article key={r.id} className="card stack">
              <div className="claim-head">
                <strong>{STATUS_TEXT[status]}</strong>
                <span className="muted small">Created {formatWhen(r.createdAt)} · expires {formatWhen(r.expiresAt)}</span>
              </div>
              <p className="small">Asks for: {r.scopes.map((s) => CLAIM_CONTENT[s].label).join("; ")}</p>
              {status === "open" && (
                <>
                  <div className="linkbox"><code>{link}</code></div>
                  <div className="row">
                    <button className="button secondary" onClick={() => copy(link, r.id)}>{copied === r.id ? "Copied" : "Copy link"}</button>
                    <Link className="button secondary" href={`/r/${r.token}`} target="_blank">Preview what they see</Link>
                    <button className="button ghost" onClick={() => revoke(r.id)}>Revoke</button>
                  </div>
                  <Notice title="Prototype only">
                    <button className="button ghost" onClick={() => simulateReply(r.id, r.scopes)}>Simulate the subletter replying</button>
                  </Notice>
                </>
              )}
            </article>
          );
        })}
      </section>
    </>
  );
}

export default function RequestPage() {
  return <CaseShell>{(kase) => <RequestPanel kase={kase} />}</CaseShell>;
}