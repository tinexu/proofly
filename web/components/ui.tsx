"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { Case, Claim, ClaimState } from "@/lib/types";
import { CLAIM_CONTENT, CORE_DISCLAIMER, EVIDENCE_KIND_LABEL, EVIDENCE_SOURCE_LABEL, STATE_LABEL } from "@/lib/content";
import { assertedFor, displayStatus } from "@/lib/rules";
import { useCase } from "@/lib/store";

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

/** Loads the case from the URL and renders the shared header + step navigation. */
export function CaseShell({ children }: { children: (kase: Case) => ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const { kase, hydrated } = useCase(params.id);

  if (!hydrated) return <p className="muted">Loading case…</p>;
  if (!kase)
    return (
      <div className="stack">
        <h1>Case not found</h1>
        <p>It may have been deleted, or it was opened in a different browser.</p>
        <Link className="button" href="/">Start a new check</Link>
      </div>
    );

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
      {children(kase)}
      <p className="disclaimer small">{CORE_DISCLAIMER}</p>
    </div>
  );
}