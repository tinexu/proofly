"use client";

// Subletter's view of an evidence request (F03 + F04 upload rules).
// Shows precisely what was requested, warns about sensitive data, and records consent.
import { useParams } from "next/navigation";
import { useState } from "react";
import type { ClaimType, Evidence, EvidenceKind, FactField, ProvidedFact } from "@/lib/types";
import { CLAIM_CONTENT, FACT_LABEL } from "@/lib/content";
import { requestStatus } from "@/lib/rules";
import { randomId } from "@/lib/ids";
import { useStore } from "@/lib/store";

const ACCEPTED = ["application/pdf", "image/png", "image/jpeg", "image/heic", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;

const KIND_FOR: Record<ClaimType, EvidenceKind> = {
  property_existence: "live_tour",
  person_unit_relationship: "lease_excerpt",
  sublet_authorization: "lease_excerpt",
  price_and_term: "message_screenshot",
  payment_destination: "message_screenshot",
};

const FACTS_FOR: Partial<Record<ClaimType, FactField[]>> = {
  price_and_term: ["monthlyRent", "deposit", "startDate", "endDate"],
  payment_destination: ["paymentMethod"],
};

export default function EvidenceRequestPage() {
  const { token } = useParams<{ token: string }>();
  const { hydrated, findRequest, updateCase } = useStore();
  const [files, setFiles] = useState<Partial<Record<ClaimType, File>>>({});
  const [facts, setFacts] = useState<Partial<Record<FactField, string>>>({});
  const [fileErrors, setFileErrors] = useState<Partial<Record<ClaimType, string>>>({});
  const [consent, setConsent] = useState(false);
  const [done, setDone] = useState(false);

  if (!hydrated) return <p className="muted">Loading…</p>;
  const found = findRequest(token);
  if (done) return <div className="stack"><h1>Thanks, it's sent.</h1><p>You can close this page. The link no longer accepts uploads.</p></div>;
  if (!found)
    return <div className="stack"><h1>This link isn't valid</h1><p>Ask the person who sent it for a new one. (In this prototype, links only work in the browser that created them.)</p></div>;

  const { kase, request } = found;
  const status = requestStatus(request);
  if (status !== "open")
    return <div className="stack"><h1>This link is no longer active</h1><p>It has {status === "responded" ? "already been used" : status}. Ask for a new link if needed.</p></div>;

  function pick(type: ClaimType, file: File | undefined) {
    if (!file) return;
    let err = "";
    if (!ACCEPTED.includes(file.type)) err = "Please upload a PDF or an image (PNG, JPG, HEIC, WebP).";
    else if (file.size > MAX_BYTES) err = "Files must be 10 MB or smaller.";
    setFileErrors((e) => ({ ...e, [type]: err }));
    setFiles((f) => ({ ...f, [type]: err ? undefined : file }));
  }

  const hasAnything = Object.values(files).some(Boolean) || Object.values(facts).some((v) => v?.trim());

  function submit() {
    if (!consent || !hasAnything) return;
    const now = new Date().toISOString();
    const evidence: Evidence[] = [];
    const provided: Partial<Record<FactField, ProvidedFact>> = {};
    for (const type of request.scopes) {
      const file = files[type];
      const typedFacts = (FACTS_FOR[type] ?? []).filter((f) => facts[f]?.trim());
      if (!file && !typedFacts.length) continue;
      const id = randomId(8);
      evidence.push({
        id,
        kind: file ? KIND_FOR[type] : "message_screenshot",
        source: "subletter",
        description: file ? `Uploaded for: ${CLAIM_CONTENT[type].label}` : `Typed details for: ${CLAIM_CONTENT[type].label}`,
        claimTypes: [type],
        addedAt: now,
        fileName: file?.name,
      });
      typedFacts.forEach((f) => { provided[f] = { value: facts[f]!.trim(), evidenceId: id }; });
    }
    updateCase(kase.id, (c) => ({
      ...c,
      evidence: [...c.evidence, ...evidence],
      providedFacts: { ...c.providedFacts, ...provided },
      claims: Object.fromEntries(Object.entries(c.claims).map(([t, cl]) => [t, request.scopes.includes(t as ClaimType) ? { ...cl, reviewer: "rules" as const } : cl])) as typeof c.claims,
      requests: c.requests.map((r) => (r.id === request.id ? { ...r, respondedAt: now } : r)),
    }), `Subletter responded with ${evidence.length} item${evidence.length === 1 ? "" : "s"}`, "subletter");
    setDone(true);
  }

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">Evidence request</p>
        <h1>Someone is checking your sublet listing</h1>
        <p className="lead">
          A person interested in your sublet asked for a few details. Sharing is your choice. Only they will see what
          you send, and they can't see anything else about you.
        </p>
      </div>

      <div className="notice notice-caution">
        <strong>Please don't share</strong>
        <ul>
          <li>Social Security numbers, bank or card details, or passwords</li>
          <li>A full photo ID. Cover ID numbers, birth dates and signatures</li>
          <li>Other tenants' personal information</li>
        </ul>
      </div>

      {request.scopes.map((type) => (
        <section key={type} className="card stack">
          <h2>{CLAIM_CONTENT[type].label}</h2>
          <p className="small">{CLAIM_CONTENT[type].requestPrompt}</p>
          <label htmlFor={`file-${type}`}>Upload a file (optional)</label>
          <input id={`file-${type}`} type="file" accept={ACCEPTED.join(",")} onChange={(e) => pick(type, e.target.files?.[0])} />
          {fileErrors[type] && <p className="error small" role="alert">{fileErrors[type]}</p>}
          {(FACTS_FOR[type] ?? []).map((f) => (
            <div key={f}>
              <label htmlFor={`fact-${f}`}>{FACT_LABEL[f]}</label>
              <input id={`fact-${f}`} type={f.endsWith("Date") ? "date" : "text"} value={facts[f] ?? ""} onChange={(e) => setFacts((s) => ({ ...s, [f]: e.target.value }))} />
            </div>
          ))}
        </section>
      ))}

      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>I choose to share these with the person who sent this link. I can ask them to delete it at any time.</span>
      </label>
      <p className="muted small">Link expires {new Date(request.expiresAt).toLocaleString()}. Prototype: files are not uploaded anywhere; only their names are recorded.</p>
      <div className="row">
        <button className="button" onClick={submit} disabled={!consent || !hasAnything}>Send</button>
      </div>
    </div>
  );
}