"use client";

// The subletter's evidence-request page (Week 6, Day 5; F03 + F04).
// No account needed. Shows only what was asked, warns about sensitive data,
// requires consent, and checks files before sending. The server checks again.
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type PublicRequest } from "@/lib/api";
import type { ClaimType } from "@/lib/types";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.heic,application/pdf,image/png,image/jpeg,image/webp,image/heic";
const OK_EXT = /\.(pdf|png|jpe?g|webp|heic)$/i;
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PER_ITEM = 3;

type Phase = "loading" | "invalid" | "form" | "sending" | "done";

export default function EvidenceRequestPage() {
  const { token } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<Phase>("loading");
  const [req, setReq] = useState<PublicRequest | null>(null);
  const [files, setFiles] = useState<Partial<Record<ClaimType, File[]>>>({});
  const [fileErrors, setFileErrors] = useState<Partial<Record<ClaimType, string>>>({});
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.lookupLink(token)
      .then((r) => { setReq(r); setPhase("form"); })
      .catch(() => setPhase("invalid"));
  }, [token]);

  function pick(type: ClaimType, list: FileList | null) {
    const chosen = Array.from(list ?? []);
    let problem = "";
    if (chosen.length > MAX_PER_ITEM) problem = `Choose at most ${MAX_PER_ITEM} files here.`;
    else if (chosen.some((f) => !OK_EXT.test(f.name))) problem = "Only PDFs and photos (PNG, JPG, WebP, HEIC).";
    else if (chosen.some((f) => f.size > MAX_BYTES)) problem = "Each file must be 10 MB or smaller.";
    else if (chosen.some((f) => f.size === 0)) problem = "One of these files is empty.";
    setFileErrors((e) => ({ ...e, [type]: problem }));
    setFiles((f) => ({ ...f, [type]: problem ? [] : chosen }));
  }

  const chosen = Object.entries(files).flatMap(([type, list]) => (list ?? []).map((file) => ({ type: type as ClaimType, file })));
  const canSend = consent && chosen.length > 0 && phase === "form";

  async function send() {
    if (!canSend) return;
    setError("");
    setPhase("sending");
    try {
      await api.submitEvidence(token, chosen);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send your files.");
      setPhase("form");
    }
  }

  if (phase === "loading") return <p className="muted" role="status">Loading…</p>;
  if (phase === "invalid")
    return (
      <div className="stack">
        <h1>This link isn&apos;t valid or has expired</h1>
        <p>Ask the person who sent it for a new one. Links work for a limited time and for one reply.</p>
      </div>
    );
  if (phase === "done")
    return (
      <div className="stack">
        <h1>Thanks, your files were sent</h1>
        <p>You can close this page. This link no longer accepts uploads.</p>
        <p className="muted small">The person who asked can open your files only after they pass a virus check.</p>
      </div>
    );

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">Evidence request</p>
        <h1>Someone is checking your sublet listing</h1>
        <p className="lead">
          A person interested in your sublet asked for a few things. Sharing is your choice. Only they will see what
          you send, and they can&apos;t see anything else about you.
        </p>
      </div>

      <div className="notice notice-caution">
        <strong>Please don&apos;t share</strong>
        <ul>
          <li>Social Security numbers, bank or card details, or passwords</li>
          <li>A full photo ID. Cover ID numbers, birth dates and signatures</li>
          <li>Other tenants&apos; personal information</li>
        </ul>
      </div>

      {req!.items.map((item) => (
        <section key={item.type} className="card stack">
          <h2>{item.label}</h2>
          <p className="small">{item.prompt}</p>
          <div className="drop">
            <label htmlFor={`file-${item.type}`}>Choose files (up to {MAX_PER_ITEM}, optional)</label>
            <input id={`file-${item.type}`} type="file" multiple accept={ACCEPT} onChange={(e) => pick(item.type, e.target.files)} disabled={phase === "sending"} />
            {fileErrors[item.type] && <p className="error small" role="alert">{fileErrors[item.type]}</p>}
            {(files[item.type]?.length ?? 0) > 0 && (
              <ul className="small">{files[item.type]!.map((f) => <li key={f.name}>{f.name}</li>)}</ul>
            )}
          </div>
        </section>
      ))}

      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={phase === "sending"} />
        <span>I choose to share these files with the person who sent this link.</span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button className="button" onClick={send} disabled={!canSend}>{phase === "sending" ? "Sending…" : "Send files"}</button>
      </div>
      <p className="muted small">
        PDFs and photos only, 10 MB each. You can send one reply; this link expires {new Date(req!.expires_at).toLocaleString()}.
      </p>
    </div>
  );
}