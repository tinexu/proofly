// Builds the exportable case summary (F06). No guarantees, always the independent-contact reminder.

import { CLAIM_TYPES, type Case, type Decision } from "./types";
import { CLAIM_CONTENT, CORE_DISCLAIMER, EVIDENCE_KIND_LABEL, FACT_LABEL, STATE_LABEL } from "./content";
import { assertedFor, findDiscrepancies, paymentFlags, unknowns } from "./rules";

export const DECISION_LABEL: Record<Decision, string> = {
  proceed_independent: "Continue, after confirming with the landlord independently",
  pause: "Pause until missing evidence arrives",
  stop: "Stop. Not continuing with this sublet",
};

export function buildSummary(c: Case): string {
  const lines: string[] = [];
  lines.push(`# Proofly case summary`);
  lines.push(``);
  lines.push(`Generated ${new Date().toLocaleString()} · Case created ${new Date(c.createdAt).toLocaleString()}`);
  lines.push(``);
  lines.push(`> ${CORE_DISCLAIMER}`);
  lines.push(``);
  lines.push(`## Offer as listed`);
  lines.push(`- Address: ${c.offer.address}`);
  lines.push(`- Terms: ${assertedFor("price_and_term", c.offer)}`);
  lines.push(`- Payment requested: ${c.offer.paymentMethod || "not stated"}`);
  lines.push(``);
  lines.push(`## Claims`);
  for (const t of CLAIM_TYPES) {
    const claim = c.claims[t];
    const ev = c.evidence.filter((e) => claim.evidenceIds.includes(e.id));
    const basis = ev.length ? ` (based on: ${ev.map((e) => EVIDENCE_KIND_LABEL[e.kind]).join(", ")})` : "";
    lines.push(`- ${CLAIM_CONTENT[t].label}: ${STATE_LABEL[claim.state]}${basis}`);
  }
  const disc = findDiscrepancies(c);
  if (disc.length) {
    lines.push(``);
    lines.push(`## Mismatches`);
    disc.forEach((d) => lines.push(`- ${FACT_LABEL[d.field]}: listing says "${d.listed}", evidence says "${d.provided}"`));
  }
  const flags = paymentFlags(c.offer);
  if (flags.length) {
    lines.push(``);
    lines.push(`## Payment notes`);
    flags.forEach((f) => lines.push(`- ${f.message} ${f.action}`));
  }
  lines.push(``);
  lines.push(`## What has NOT been verified`);
  unknowns(c).forEach((u) => lines.push(`- ${u}`));
  lines.push(``);
  lines.push(`## Decision`);
  lines.push(c.decision ? `- ${DECISION_LABEL[c.decision]}` : `- No decision recorded`);
  if (c.decisionNote) lines.push(`- Note: ${c.decisionNote}`);
  lines.push(``);
  lines.push(`Verify using independent contact info before paying. This summary is not a guarantee and not legal advice.`);
  return lines.join("\n");
}