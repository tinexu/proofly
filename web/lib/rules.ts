// Display helpers for the trust model. The API's rules engine (api/app/rules.py) decides
// claim states and compares facts; these pure functions only present what it decided.

import {
  CLAIM_TYPES,
  FACT_FIELDS,
  type Case,
  type ClaimState,
  type ClaimType,
  type DisplayStatus,
  type Evidence,
  type FactField,
  type Offer,
} from "./types";
import { CLAIM_CONTENT, EVIDENCE_KIND_LABEL, FACT_CLAIM, PERMISSION_LABEL, ROLE_LABEL } from "./content";

export function displayStatus(state: ClaimState): DisplayStatus {
  if (state === "SUPPORTED") return "supported";
  if (state === "CONFLICTING") return "conflicting";
  return "unresolved";
}

function formatMoney(v: string) {
  return v ? `$${v.replace(/^\$/, "")}` : "not stated";
}

/** What the listing or subletter asserted for each claim, in plain words. */
export function assertedFor(type: ClaimType, offer: Offer): string {
  switch (type) {
    case "property_existence":
      return offer.address || "No address given yet";
    case "person_unit_relationship":
      return `${ROLE_LABEL[offer.claimedRole]}${offer.contactHandle ? ` (${offer.contactHandle})` : ""}`;
    case "sublet_authorization":
      return PERMISSION_LABEL[offer.permissionClaim];
    case "price_and_term":
      return `${formatMoney(offer.monthlyRent)}/month, ${offer.startDate || "?"} to ${offer.endDate || "?"}, deposit ${formatMoney(offer.deposit)}`;
    case "payment_destination":
      return offer.paymentMethod || "Not stated yet";
  }
}

// ---------------------------------------------------------------------------
// Discrepancies (F05): each mismatching field is its own actionable item.

export interface Discrepancy {
  field: FactField;
  claimType: ClaimType;
  listed: string;
  provided: string;
  evidenceId: string;
}

export const MONEY_FACTS: FactField[] = ["monthlyRent", "deposit"];
export const DATE_FACTS: FactField[] = ["startDate", "endDate"];

/** Shows a fact value the way people write it: $1,200 and Jan 5, 2027. */
export function formatFact(field: FactField, value: string | undefined): string {
  if (!value) return "Not stated";
  if (MONEY_FACTS.includes(field)) {
    const n = Number(value.replace(/[$,]/g, ""));
    return Number.isFinite(n) ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : value;
  }
  if (DATE_FACTS.includes(field)) {
    const d = new Date(`${value}T00:00:00`);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
  return value;
}

/** Facts where a file and the listing disagree. The API does the comparing (api/app/facts.py). */
export function findDiscrepancies(c: Case): Discrepancy[] {
  const out: Discrepancy[] = [];
  for (const field of FACT_FIELDS) {
    const fact = c.providedFacts[field];
    if (fact?.result !== "differs") continue;
    out.push({ field, claimType: FACT_CLAIM[field], listed: fact.listed ?? "", provided: fact.value, evidenceId: fact.evidenceId });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Payment flags: neutral, explainable, never a fraud accusation.

const HARD_TO_REVERSE = [
  { pattern: /wire|western union|moneygram/i, name: "a wire transfer" },
  { pattern: /gift ?card/i, name: "gift cards" },
  { pattern: /crypto|bitcoin|btc|usdt|eth\b/i, name: "cryptocurrency" },
  { pattern: /zelle|venmo|cash ?app|paypal friends/i, name: "a person-to-person payment app" },
];

export interface Flag {
  claimType: ClaimType;
  message: string;
  action: string;
}

export function paymentFlags(offer: Offer): Flag[] {
  const hit = HARD_TO_REVERSE.find((h) => h.pattern.test(offer.paymentMethod));
  if (!hit) return [];
  return [
    {
      claimType: "payment_destination",
      message: `Payment was requested through ${hit.name}. These payments are usually hard to reverse if something goes wrong.`,
      action:
        "Before paying, confirm the unit and the sublet with the landlord or property manager using contact info you found yourself.",
    },
  ];
}

// ---------------------------------------------------------------------------
// Evidence and claims. Claim states come from the API's rules engine (api/app/rules.py).

export function evidenceFor(c: Case, type: ClaimType): Evidence[] {
  return c.evidence.filter((e) => e.claimTypes.includes(type));
}

/** The file a "supported" review names, if any. */
export function supportingFile(c: Case, type: ClaimType): Evidence | undefined {
  const id = c.claims[type].supportedBy;
  return id ? c.evidence.find((e) => e.id === id) : undefined;
}

/** Everything that remains unknown: unconfirmed claims + limits of the evidence we do have. */
export function unknowns(c: Case): string[] {
  const out: string[] = [];
  for (const type of CLAIM_TYPES) {
    const claim = c.claims[type];
    if (claim.state !== "SUPPORTED") {
      out.push(CLAIM_CONTENT[type].unknown);
      continue;
    }
    // Supported is the renter's judgement of one file; say what that file can't show.
    const file = supportingFile(c, type);
    if (file) {
      out.push(`${CLAIM_CONTENT[type].label}: supported by your review of "${file.fileName ?? EVIDENCE_KIND_LABEL[file.kind]}". Not confirmed: whether that file is genuine, current, or about this unit.`);
    } else {
      out.push(`${CLAIM_CONTENT[type].label}: supported by your review of a file. Not confirmed: whether that file is genuine, current, or about this unit.`);
    }
  }
  return out;
}

export function progress(c: Case) {
  const states = CLAIM_TYPES.map((t) => displayStatus(c.claims[t].state));
  return {
    total: states.length,
    supported: states.filter((s) => s === "supported").length,
    conflicting: states.filter((s) => s === "conflicting").length,
    unresolved: states.filter((s) => s === "unresolved").length,
  };
}

export function requestStatus(r: { expiresAt: string; revokedAt?: string; respondedAt?: string }, now = Date.now()) {
  if (r.revokedAt) return "revoked" as const;
  if (r.respondedAt) return "responded" as const;
  if (new Date(r.expiresAt).getTime() < now) return "expired" as const;
  return "open" as const;
}