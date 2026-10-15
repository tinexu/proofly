// A fictional demo case for usability sessions. It deliberately shows each status:
// one supported claim, one conflict, one payment flag, and several unknowns.

import { CLAIM_TYPES, type Case, type Claim, type ClaimType, type Offer } from "./types";
import { applyRules } from "./rules";

export const SAMPLE_CASE_ID = "sample";

export function emptyClaims(now: string): Record<ClaimType, Claim> {
  return Object.fromEntries(
    CLAIM_TYPES.map((type) => [
      type,
      { type, state: "UNCHECKED", evidenceIds: [], reviewer: "rules", updatedAt: now } satisfies Claim,
    ]),
  ) as unknown as Record<ClaimType, Claim>;
}

export function createSampleCase(): Case {
  const day = (offsetHours: number) => new Date(Date.now() - offsetHours * 3_600_000).toISOString();

  const offer: Offer = {
    address: "214 Elm Street, Unit 3B, College Town",
    startDate: "2027-01-05",
    endDate: "2027-04-30",
    monthlyRent: "850",
    deposit: "500",
    platform: "facebook",
    platformSuggested: false,
    sourceUrl: "https://www.facebook.com/groups/example-housing/posts/123",
    claimedRole: "leaseholder",
    contactHandle: "Jordan (Messenger)",
    permissionClaim: "says_approved",
    paymentMethod: "Zelle deposit to hold the room before a tour",
  };

  const base: Case = {
    id: SAMPLE_CASE_ID,
    createdAt: day(26),
    offer,
    claims: emptyClaims(day(26)),
    evidence: [
      {
        id: "ev_public",
        kind: "address_match",
        source: "public_record",
        description: "Address matches a residential parcel in county records.",
        claimTypes: ["property_existence"],
        addedAt: day(25),
      },
      {
        id: "ev_lease",
        kind: "lease_excerpt",
        source: "subletter",
        description: "First page of a lease, name partly covered.",
        claimTypes: ["person_unit_relationship", "price_and_term"],
        addedAt: day(4),
        fileName: "lease-page-1.pdf",
      },
    ],
    providedFacts: {
      monthlyRent: { value: "950", evidenceId: "ev_lease" },
      address: { value: "214 Elm Street, Unit 3B, College Town", evidenceId: "ev_lease" },
    },
    requests: [
      {
        id: "req_1",
        token: "sampletoken7xk2m9q4",
        scopes: ["person_unit_relationship", "sublet_authorization"],
        createdAt: day(24),
        expiresAt: day(-48),
        respondedAt: day(4),
      },
    ],
    events: [
      { id: "e1", at: day(26), actor: "you", action: "Created case from a Facebook listing" },
      { id: "e2", at: day(25), actor: "rules", action: "Address found in public records" },
      { id: "e3", at: day(24), actor: "you", action: "Sent an evidence request (expires in 72 hours)" },
      { id: "e4", at: day(4), actor: "subletter", action: "Uploaded lease-page-1.pdf" },
      { id: "e5", at: day(4), actor: "rules", action: "Rent on the lease ($950) differs from the listing ($850)" },
    ],
  };
  return applyRules(base);
}