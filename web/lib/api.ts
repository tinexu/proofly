// Talks to the Proofly API (Week 4, Day 9). The session cookie is HttpOnly, so this
// code never sees it; `credentials: "include"` makes the browser send it.

import { CLAIM_TYPES, type Case, type ClaimState, type ClaimType, type ClaimedRole, type Decision, type Offer, type PermissionClaim, type Platform } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Turn FastAPI's error body into one readable sentence. */
function messageFrom(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { msg?: string }) => (d.msg ?? "Invalid value").replace(/^Value error, /, ""))
      .join(" ");
  }
  if (status === 0) return "Can't reach the Proofly API. Is it running?";
  return `Something went wrong (${status}).`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, messageFrom(0, null));
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageFrom(res.status, data));
  return data as T;
}

// ---------------------------------------------------------------------------
// Shapes returned by the API

export interface ApiUser {
  id: string;
  email: string;
}

export interface ApiClaim {
  type: ClaimType;
  state: ClaimState;
  rationale: string | null;
  reviewer: "rules" | "user";
  reviewed_by_id: string | null;
  updated_at: string;
}

export interface ApiCase {
  id: string;
  created_at: string;
  updated_at: string;
  address: string;
  start_date: string | null;
  end_date: string | null;
  monthly_rent: string | null;
  deposit: string | null;
  platform: Platform;
  source_url: string | null;
  claimed_role: ClaimedRole;
  contact_handle: string | null;
  permission_claim: PermissionClaim;
  payment_method: string | null;
  decision: Decision | null;
  decision_note: string | null;
  claims: ApiClaim[];
}

export interface ApiCaseSummary {
  id: string;
  address: string;
  created_at: string;
}

export interface ApiActivity {
  at: string;
  actor: "you" | "subletter" | "rules" | "system";
  action: string;
  description: string;
}

/** States a renter may set by hand. "Supported" needs evidence, which arrives in Week 6. */
export type ReviewState = "REVIEW_NEEDED" | "CONFLICTING";

// ---------------------------------------------------------------------------
// Endpoints

export const api = {
  me: () => request<ApiUser>("GET", "/auth/me"),
  requestLink: (email: string) => request<{ status: string; message: string }>("POST", "/auth/magic-link", { email }),
  verify: (token: string) => request<{ user: ApiUser; new_account: boolean }>("POST", "/auth/verify", { token }),
  logout: () => request<void>("POST", "/auth/logout"),

  listCases: () => request<ApiCaseSummary[]>("GET", "/cases"),
  createCase: (offer: Offer) => request<ApiCase>("POST", "/cases", offerToApi(offer)),
  getCase: (id: string) => request<ApiCase>("GET", `/cases/${encodeURIComponent(id)}`),
  activity: (id: string) => request<ApiActivity[]>("GET", `/cases/${encodeURIComponent(id)}/activity`),
  deleteCase: (id: string) => request<void>("DELETE", `/cases/${encodeURIComponent(id)}`),
  setDecision: (id: string, decision: Decision | null, note: string) =>
    request<ApiCase>("PUT", `/cases/${encodeURIComponent(id)}/decision`, { decision, decision_note: note || null }),

  reviewClaim: (id: string, type: ClaimType, state: ReviewState, rationale: string) =>
    request<ApiCase>("PATCH", `/cases/${encodeURIComponent(id)}/claims/${type}`, { state, rationale }),
  clearReview: (id: string, type: ClaimType) =>
    request<ApiCase>("DELETE", `/cases/${encodeURIComponent(id)}/claims/${type}/review`),
};

// ---------------------------------------------------------------------------
// Converting between the API and the screens' Case shape (lib/types.ts)

const blankToNull = (v: string) => (v.trim() ? v.trim() : null);

export function offerToApi(o: Offer) {
  return {
    address: o.address.trim(),
    start_date: o.startDate || null,
    end_date: o.endDate || null,
    monthly_rent: blankToNull(o.monthlyRent),
    deposit: blankToNull(o.deposit),
    platform: o.platform,
    source_url: blankToNull(o.sourceUrl),
    claimed_role: o.claimedRole,
    contact_handle: blankToNull(o.contactHandle),
    permission_claim: o.permissionClaim,
    payment_method: blankToNull(o.paymentMethod),
  };
}

const money = (v: string | null) => (v ? String(Number(v)) : "");

export function caseFromApi(c: ApiCase, activity: ApiActivity[] = []): Case {
  const byType = new Map(c.claims.map((cl) => [cl.type, cl]));
  return {
    id: c.id,
    createdAt: c.created_at,
    offer: {
      address: c.address,
      startDate: c.start_date ?? "",
      endDate: c.end_date ?? "",
      monthlyRent: money(c.monthly_rent),
      deposit: money(c.deposit),
      platform: c.platform,
      platformSuggested: false,
      sourceUrl: c.source_url ?? "",
      claimedRole: c.claimed_role,
      contactHandle: c.contact_handle ?? "",
      permissionClaim: c.permission_claim,
      paymentMethod: c.payment_method ?? "",
    },
    claims: Object.fromEntries(
      CLAIM_TYPES.map((t) => {
        const cl = byType.get(t);
        return [t, {
          type: t,
          state: cl?.state ?? "UNCHECKED",
          evidenceIds: [],
          rationale: cl?.rationale ?? undefined,
          reviewer: cl?.reviewer ?? "rules",
          updatedAt: cl?.updated_at ?? c.created_at,
        }];
      }),
    ) as unknown as Case["claims"],
    // Evidence and evidence requests arrive in Week 6.
    evidence: [],
    providedFacts: {},
    requests: [],
    decision: c.decision ?? undefined,
    decisionNote: c.decision_note ?? undefined,
    events: activity.map((a, i) => ({ id: `${a.at}-${i}`, at: a.at, actor: a.actor, action: a.description })),
  };
}