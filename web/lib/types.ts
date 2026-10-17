// Domain types for the prototype. These mirror the spec's trust model (section 08)
// and data model (section 10) so the backend in Stage 3 can adopt the same shapes.

export const CLAIM_TYPES = [
  "property_existence",
  "person_unit_relationship",
  "sublet_authorization",
  "price_and_term",
  "payment_destination",
] as const;
export type ClaimType = (typeof CLAIM_TYPES)[number];

export type ClaimState =
  | "UNCHECKED"
  | "EVIDENCE_SUBMITTED"
  | "REVIEW_NEEDED"
  | "SUPPORTED"
  | "CONFLICTING";

/** The three statuses S3 shows to the renter. */
export type DisplayStatus = "supported" | "unresolved" | "conflicting";

export type EvidenceKind =
  | "address_match"
  | "school_email"
  | "lease_excerpt"
  | "manager_confirmation"
  | "live_tour"
  | "message_screenshot"
  | "uploaded_file";

export type EvidenceSource = "public_record" | "subletter" | "renter" | "independent_contact";

export type ScanStatus = "pending_scan" | "clean" | "infected" | "scan_error";

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  source: EvidenceSource;
  description: string;
  claimTypes: ClaimType[];
  addedAt: string;
  fileName?: string;
  /** Uploaded files only (Week 6): virus-check status and where to download it once clean. */
  scanStatus?: ScanStatus;
  downloadUrl?: string;
  sizeBytes?: number;
  /** The evidence link it came through, if any. */
  requestId?: string;
}

export interface Claim {
  type: ClaimType;
  state: ClaimState;
  evidenceIds: string[];
  rationale?: string;
  /** "rules" = set by the rules engine; "user" = manual override with provenance. */
  reviewer: "rules" | "user";
  updatedAt: string;
}

export type Platform = "facebook" | "instagram" | "reddit" | "discord" | "group_chat" | "other";
export type ClaimedRole = "leaseholder" | "roommate" | "manager" | "not_stated";
export type PermissionClaim = "says_approved" | "says_not_needed" | "not_mentioned";

export interface Offer {
  address: string;
  startDate: string;
  endDate: string;
  monthlyRent: string;
  deposit: string;
  platform: Platform;
  /** True when the platform was guessed from the URL and not yet confirmed. */
  platformSuggested: boolean;
  sourceUrl: string;
  claimedRole: ClaimedRole;
  contactHandle: string;
  permissionClaim: PermissionClaim;
  paymentMethod: string;
}

/** Offer fields that can be compared against evidence for discrepancies. */
export const FACT_FIELDS = [
  "address",
  "startDate",
  "endDate",
  "monthlyRent",
  "deposit",
  "paymentMethod",
] as const;
export type FactField = (typeof FACT_FIELDS)[number];

export interface ProvidedFact {
  value: string;
  evidenceId: string;
  /** Renter reviewed the mismatch and chose to keep the listing value. */
  acknowledged?: boolean;
}

export interface EvidenceRequest {
  id: string;
  token: string;
  scopes: ClaimType[];
  createdAt: string;
  expiresAt: string;
  revokedAt?: string;
  respondedAt?: string;
}

export type Decision = "proceed_independent" | "pause" | "stop";

export interface AuditEvent {
  id: string;
  at: string;
  actor: "you" | "subletter" | "rules" | "system";
  action: string;
}

export interface Case {
  id: string;
  createdAt: string;
  offer: Offer;
  claims: Record<ClaimType, Claim>;
  evidence: Evidence[];
  providedFacts: Partial<Record<FactField, ProvidedFact>>;
  requests: EvidenceRequest[];
  decision?: Decision;
  decisionNote?: string;
  events: AuditEvent[];
}