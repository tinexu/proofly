"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Case, Claim, ClaimState, Evidence } from "@/lib/types";
import { CLAIM_CONTENT, CORE_DISCLAIMER, EVIDENCE_KIND_LABEL, EVIDENCE_SOURCE_LABEL, SCAN_LABEL, STATE_LABEL } from "@/lib/content";
import { assertedFor, displayStatus } from "@/lib/rules";
import { ApiError, api, caseFromApi, type ApiCase } from "@/lib/api";
import { RequireAuth } from "@/lib/auth";

export function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Status shown with a shape + text, never color alone, and never a green clearance badge. */
export function StatusBadge({ state }: { state: ClaimState }) {
  const status = displayStatus(state);
  const glyph = status === "supported" ? "●" : status === "conflicting" ? "▲" : "○";
  return (
    <span className={`badge badge-${status}`}>
      <span aria-hidden="true">{glyph}</span> {STATE_LABEL[state]}
    </span>
  );
}

export function Notice({ tone = "neutral", title, children }: { tone?: "neutral" | "caution"; title?: string; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "caution" ? "note" : undefined}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

function formatSize(bytes?: number) {
  if (!bytes) return "";
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** One uploaded file: its name, virus-check status, and a download link once it's clean. */
export function FileLine({ e }: { e: Evidence }) {
  if (!e.scanStatus) return null;
  return (
    <span className="file-line small block">
      {e.downloadUrl ? (
        <a href={e.downloadUrl} rel="noopener noreferrer">{e.fileName}</a>
      ) : (
        <span>{e.fileName}</span>
      )}
      <span className="muted"> · {formatSize(e.sizeBytes)} · </span>
      <span className={`scan scan-${e.scanStatus}`}>{SCAN_LABEL[e.scanStatus]}</span>
    </span>
  );
}

export function ClaimCard({ kase, claim }: { kase: Case; claim: Claim }) {
  const content = CLAIM_CONTENT[claim.type];
  const evidence = kase.evidence.filter((e) => claim.evidenceIds.includes(e.id));
  return (
    <article className="card claim">
      <header className="claim-head">
        <h3>{content.label}</h3>
        <StatusBadge state={claim.state} />
      </header>
      <p className="muted small">Claimed: {assertedFor(claim.type, kase.offer)}</p>

      {evidence.length > 0 && (
        <ul className="evidence-list">
          {evidence.map((e) => (
            <li key={e.id}>
              <span>{claim.state === "SUPPORTED" ? "Supported by " : "Evidence: "}</span>
              <strong>{EVIDENCE_KIND_LABEL[e.kind]}</strong>
              <span className="muted"> · {EVIDENCE_SOURCE_LABEL[e.source]} · {formatWhen(e.addedAt)}</span>
              {e.scanStatus && <FileLine e={e} />}
            </li>
          ))}
        </ul>
      )}
      {claim.rationale && <p className="small">{claim.rationale}</p>}
      {claim.reviewer === "user" && <p className="muted small">Marked by you on {formatWhen(claim.updatedAt)}.</p>}
      {claim.state !== "SUPPORTED" && <p className="unknown small">{content.unknown}</p>}
    </article>
  );
}

const STEPS = [
  { href: "", label: "Checklist", code: "S3" },
  { href: "/request", label: "Request evidence", code: "S4" },
  { href: "/review", label: "Compare & review", code: "S5" },
  { href: "/summary", label: "Decision", code: "S6" },
];

export interface CaseContext {
  /** Re-fetch the case and its activity from the API. */
  reload: () => Promise<void>;
  /** Use a case the API just returned (saves a round trip), then refresh activity. */
  update: (fresh: ApiCase) => Promise<void>;
}

function LoadedCase({ id, children }: { id: string; children: (kase: Case, ctx: CaseContext) => ReactNode }) {
  const pathname = usePathname();
  const [kase, setKase] = useState<Case | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);

  const load = useCallback(async (fresh?: ApiCase) => {
    try {
      const [c, activity, files, links] = await Promise.all([
        fresh ? Promise.resolve(fresh) : api.getCase(id),
        api.activity(id),
        api.listEvidence(id),
        api.listRequests(id),
      ]);
      setKase(caseFromApi(c, activity, files, links));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: String(e) });
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const ctx = useMemo<CaseContext>(() => ({ reload: () => load(), update: (fresh) => load(fresh) }), [load]);

  if (error)
    return (
      <div className="stack">
        <h1>{error.status === 404 || error.status === 422 ? "Case not found" : "Can't load this case"}</h1>
        <p>{error.status === 404 || error.status === 422 ? "It may have been deleted, or it belongs to a different account." : error.message}</p>
        <Link className="button" href="/cases">Back to my cases</Link>
      </div>
    );
  if (!kase) return <p className="muted">Loading case…</p>;

  const base = `/case/${kase.id}`;
  return (
    <div className="stack">
      <div>
        <p className="eyebrow">Your sublet check</p>
        <h1 className="case-title">{kase.offer.address || "Untitled offer"}</h1>
      </div>
      <nav aria-label="Case steps" className="steps">
        {STEPS.map((s) => {
          const href = base + s.href;
          const active = pathname === href;
          return (
            <Link key={s.code} href={href} aria-current={active ? "page" : undefined} className={active ? "step active" : "step"}>
              {s.label}
            </Link>
          );
        })}
      </nav>
      {children(kase, ctx)}
      <p className="disclaimer small">{CORE_DISCLAIMER}</p>
    </div>
  );
}

/** Loads the case named in the URL (signed in, your own case) with header + step navigation. */
export function CaseShell({ children }: { children: (kase: Case, ctx: CaseContext) => ReactNode }) {
  const params = useParams<{ id: string }>();
  return (
    <RequireAuth>
      <LoadedCase id={params.id}>{children}</LoadedCase>
    </RequireAuth>
  );
}