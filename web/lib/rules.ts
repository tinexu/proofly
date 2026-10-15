// Explicit, rules-based evaluation (spec section 09: rules first, AI never decides).
// Every function here is pure so it can be unit-tested and later ported to the API.

import {
    CLAIM_TYPES,
    FACT_FIELDS,
    type Case,
    type ClaimState,
    type ClaimType,
    type DisplayStatus,
    type Evidence,
    type EvidenceKind,
    type EvidenceSource,
    type FactField,
    type Offer,
  } from "./types";
  import { CLAIM_CONTENT, FACT_CLAIM, PERMISSION_LABEL, ROLE_LABEL, SIGNALS } from "./content";
  
  export function displayStatus(state: ClaimState): DisplayStatus {
    if (state === "SUPPORTED") return "supported";
    if (state === "CONFLICTING") return "conflicting";
    return "unresolved";
  }
  
  export function normalize(value: string): string {
    return value.toLowerCase().replace(/[$,]/g, "").replace(/\s+/g, " ").trim();
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
  
  export function findDiscrepancies(c: Case, includeAcknowledged = false): Discrepancy[] {
    const out: Discrepancy[] = [];
    for (const field of FACT_FIELDS) {
      const fact = c.providedFacts[field];
      if (!fact) continue;
      if (fact.acknowledged && !includeAcknowledged) continue;
      const listed = c.offer[field];
      if (normalize(listed) !== normalize(fact.value)) {
        out.push({
          field,
          claimType: FACT_CLAIM[field],
          listed,
          provided: fact.value,
          evidenceId: fact.evidenceId,
        });
      }
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
  // Which evidence may move a claim to SUPPORTED automatically. Everything else
  // waits for the renter's review (EVIDENCE_SUBMITTED), which is deliberately conservative.
  
  const AUTO_SUPPORT: { kind: EvidenceKind; source: EvidenceSource; claim: ClaimType }[] = [
    { kind: "address_match", source: "public_record", claim: "property_existence" },
    { kind: "manager_confirmation", source: "independent_contact", claim: "sublet_authorization" },
  ];
  
  export function evidenceFor(c: Case, type: ClaimType): Evidence[] {
    return c.evidence.filter((e) => e.claimTypes.includes(type));
  }
  
  /** Re-derive rule-owned claim states. Manual (user) assessments are left alone. */
  export function applyRules(c: Case, now = new Date().toISOString()): Case {
    const discrepancies = findDiscrepancies(c);
    const flags = paymentFlags(c.offer);
    const claims = { ...c.claims };
  
    for (const type of CLAIM_TYPES) {
      const current = claims[type];
      if (current.reviewer === "user") continue;
  
      const ev = evidenceFor(c, type);
      let state: ClaimState = "UNCHECKED";
      let rationale: string | undefined;
      let supportIds: string[] = ev.map((e) => e.id);
  
      if (discrepancies.some((d) => d.claimType === type)) {
        state = "CONFLICTING";
        rationale = "Details from the evidence don't match the listing.";
      } else if (type === "payment_destination" && flags.length) {
        state = "REVIEW_NEEDED";
        rationale = flags[0].message;
      } else {
        const auto = ev.filter((e) =>
          AUTO_SUPPORT.some((r) => r.kind === e.kind && r.source === e.source && r.claim === type),
        );
        if (auto.length) {
          state = "SUPPORTED";
          supportIds = auto.map((e) => e.id);
          rationale = auto.map((e) => SIGNALS[e.kind].supports).join(" ");
        } else if (ev.length) {
          state = "EVIDENCE_SUBMITTED";
        }
      }
  
      if (state !== current.state || rationale !== current.rationale) {
        claims[type] = { ...current, state, rationale, evidenceIds: supportIds, updatedAt: now };
      }
    }
    return { ...c, claims };
  }
  
  /** Everything that remains unknown: unconfirmed claims + limits of the evidence we do have. */
  export function unknowns(c: Case): string[] {
    const out: string[] = [];
    for (const type of CLAIM_TYPES) {
      const claim = c.claims[type];
      if (claim.state !== "SUPPORTED") {
        out.push(CLAIM_CONTENT[type].unknown);
      } else {
        const kinds = new Set(
          c.evidence.filter((e) => claim.evidenceIds.includes(e.id)).map((e) => e.kind),
        );
        kinds.forEach((k) => out.push(`${CLAIM_CONTENT[type].label}: ${SIGNALS[k].doesNotProve}`));
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