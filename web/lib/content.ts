// All user-facing copy that describes claims and evidence lives here so it can be
// reviewed (and linted by scripts/check-copy.mjs) in one place.
// Principle: say what the evidence shows, what it does NOT show, and what to do next.

import type {
    ClaimType,
    ClaimedRole,
    EvidenceKind,
    EvidenceSource,
    FactField,
    PermissionClaim,
    Platform,
    ClaimState,
  } from "./types";
  
  export const CLAIM_CONTENT: Record<
    ClaimType,
    {
      label: string;
      question: string;
      unknown: string;
      requestPrompt: string;
      independentChecks: string[];
    }
  > = {
    property_existence: {
      label: "The unit exists",
      question: "Is this a real address and unit?",
      unknown: "We have not confirmed this address or unit exists.",
      requestPrompt:
        "A short live video or recent photo that shows the unit number or building entrance.",
      independentChecks: [
        "Look up the address on a map and in your county's public property records.",
        "Run a reverse image search on the listing photos to see if they appear in other listings.",
      ],
    },
    person_unit_relationship: {
      label: "This person lives there or controls the lease",
      question: "Is this person actually connected to the unit?",
      unknown: "We have not confirmed this person is on the lease or lives in the unit.",
      requestPrompt:
        "A lease excerpt showing their name and the unit address. Cover rent amounts, signatures and ID numbers if you prefer.",
      independentChecks: [
        "Ask for a live video walkthrough where they show the unit door and number.",
        "Check that the name on any lease excerpt matches the person you are messaging.",
      ],
    },
    sublet_authorization: {
      label: "Subletting is allowed",
      question: "Has the landlord or property manager allowed this sublet?",
      unknown: "We have not confirmed the landlord or property manager allows this sublet.",
      requestPrompt:
        "Any written permission to sublet from the landlord or property manager, or the lease clause about subletting.",
      independentChecks: [
        "Find the landlord or property manager's phone or email yourself (building website, county records). Don't rely only on contact info the subletter gives you.",
        "Ask them directly whether this unit can be sublet for your dates.",
      ],
    },
    price_and_term: {
      label: "Price and dates match",
      question: "Do the rent, deposit and dates match everywhere?",
      unknown: "We have not confirmed the rent, deposit and dates are consistent.",
      requestPrompt:
        "A message or document confirming the monthly rent, deposit, move-in and move-out dates.",
      independentChecks: [
        "Get rent, deposit, dates and utilities in writing, in one place.",
        "Compare them with the original listing and with what the landlord tells you.",
      ],
    },
    payment_destination: {
      label: "Where the money goes",
      question: "Who receives the payment, and can it be reversed if something goes wrong?",
      unknown: "We have not confirmed who would receive your payment.",
      requestPrompt: "How and to whom the deposit and rent would be paid.",
      independentChecks: [
        "Don't pay by wire transfer, gift card or cryptocurrency.",
        "Pay only after you've confirmed the unit and the sublet with the landlord or property manager.",
      ],
    },
  };
  
  export const STATE_LABEL: Record<ClaimState, string> = {
    UNCHECKED: "Not checked yet",
    EVIDENCE_SUBMITTED: "Evidence received, not reviewed",
    REVIEW_NEEDED: "Needs your review",
    SUPPORTED: "Supported",
    CONFLICTING: "Conflicting",
  };
  
  export const EVIDENCE_KIND_LABEL: Record<EvidenceKind, string> = {
    address_match: "Address found in public records",
    school_email: "School email confirmed",
    lease_excerpt: "Lease excerpt",
    manager_confirmation: "Confirmation from property manager",
    live_tour: "Live tour or recent images",
    message_screenshot: "Message screenshot",
  };
  
  export const EVIDENCE_SOURCE_LABEL: Record<EvidenceSource, string> = {
    public_record: "public record",
    subletter: "provided by the subletter",
    renter: "added by you",
    independent_contact: "contact you found independently",
  };
  
  /** Spec table: what each signal supports and what it does NOT prove. */
  export const SIGNALS: Record<EvidenceKind, { supports: string; doesNotProve: string }> = {
    address_match: {
      supports: "The address appears to exist.",
      doesNotProve: "That it's available, or that anyone may sublet it.",
    },
    school_email: {
      supports: "The person controls a school email account.",
      doesNotProve: "Their identity, honesty, or that they're on the lease.",
    },
    lease_excerpt: {
      supports: "A document appears to connect someone to the property.",
      doesNotProve: "That the document is authentic or still in effect.",
    },
    manager_confirmation: {
      supports: "An independent contact says the sublet terms are allowed.",
      doesNotProve: "Anything about the payment, and it can be spoofed unless you found the contact yourself.",
    },
    live_tour: {
      supports: "What the unit looked like at one moment.",
      doesNotProve: "A legal right to rent it, or that there's no fraud.",
    },
    message_screenshot: {
      supports: "What someone wrote to you.",
      doesNotProve: "That what they wrote is true.",
    },
  };
  
  export const PLATFORM_LABEL: Record<Platform, string> = {
    facebook: "Facebook",
    instagram: "Instagram",
    reddit: "Reddit",
    discord: "Discord",
    group_chat: "Group chat",
    other: "Somewhere else",
  };
  
  export const ROLE_LABEL: Record<ClaimedRole, string> = {
    leaseholder: "Says they're the leaseholder",
    roommate: "Says they're a roommate on the lease",
    manager: "Says they manage the property",
    not_stated: "Didn't say",
  };
  
  export const PERMISSION_LABEL: Record<PermissionClaim, string> = {
    says_approved: "Says the landlord approved it",
    says_not_needed: "Says approval isn't needed",
    not_mentioned: "Didn't mention it",
  };
  
  export const FACT_LABEL: Record<FactField, string> = {
    address: "Address",
    startDate: "Move-in date",
    endDate: "Move-out date",
    monthlyRent: "Monthly rent",
    deposit: "Deposit",
    paymentMethod: "Payment method",
  };
  
  export const FACT_CLAIM: Record<FactField, ClaimType> = {
    address: "property_existence",
    startDate: "price_and_term",
    endDate: "price_and_term",
    monthlyRent: "price_and_term",
    deposit: "price_and_term",
    paymentMethod: "payment_destination",
  };
  
  export const CORE_DISCLAIMER =
    "Completing this checklist is not a safety guarantee. Verify using independent contact info before paying.";