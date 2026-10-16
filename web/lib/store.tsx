"use client";

// Prototype-only state: cases live in this browser (localStorage), nothing is sent to a
// server. Tabs stay in sync so "Preview what they see" works in a new tab.
// Stage 3 replaces this provider with calls to the FastAPI backend.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Case, EvidenceRequest, Offer } from "./types";
import { applyRules } from "./rules";
import { randomId } from "./ids";
import { SAMPLE_CASE_ID, createSampleCase, emptyClaims } from "./sample";

const STORAGE_KEY = "proofly.prototype.v1";

type Cases = Record<string, Case>;
type Actor = "you" | "subletter" | "rules";

interface StoreValue {
  hydrated: boolean;
  cases: Cases;
  createCase: (offer: Offer) => string;
  /** Apply a change, re-run rules, and append an audit event. */
  updateCase: (id: string, change: (c: Case) => Case, action: string, actor?: Actor) => void;
  deleteCase: (id: string) => void;
  resetSample: () => void;
  findRequest: (token: string) => { kase: Case; request: EvidenceRequest } | undefined;
}

const StoreContext = createContext<StoreValue | null>(null);

function load(): Cases {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Cases;
  } catch {
    /* storage unavailable: fall through to a fresh sample */
  }
  return { [SAMPLE_CASE_ID]: createSampleCase() };
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [cases, setCases] = useState<Cases>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setCases(load());
    setHydrated(true);
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setCases(load());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      const serialized = JSON.stringify(cases);
      if (localStorage.getItem(STORAGE_KEY) !== serialized) localStorage.setItem(STORAGE_KEY, serialized);
    } catch {
      /* ignore: prototype still works in memory */
    }
  }, [cases, hydrated]);

  const createCase = useCallback((offer: Offer) => {
    const id = randomId(16);
    const now = new Date().toISOString();
    const kase = applyRules({
      id,
      createdAt: now,
      offer,
      claims: emptyClaims(now),
      evidence: [],
      providedFacts: {},
      requests: [],
      events: [{ id: randomId(8), at: now, actor: "you", action: "Created case" }],
    });
    setCases((prev) => ({ ...prev, [id]: kase }));
    return id;
  }, []);

  const updateCase = useCallback<StoreValue["updateCase"]>((id, change, action, actor = "you") => {
    setCases((prev) => {
      const current = prev[id];
      if (!current) return prev;
      const now = new Date().toISOString();
      const next = applyRules(change(current), now);
      next.events = [...next.events, { id: randomId(8), at: now, actor, action }];
      return { ...prev, [id]: next };
    });
  }, []);

  const deleteCase = useCallback((id: string) => {
    setCases((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const resetSample = useCallback(() => {
    setCases((prev) => ({ ...prev, [SAMPLE_CASE_ID]: createSampleCase() }));
  }, []);

  const findRequest = useCallback(
    (token: string) => {
      for (const kase of Object.values(cases)) {
        const request = kase.requests.find((r) => r.token === token);
        if (request) return { kase, request };
      }
      return undefined;
    },
    [cases],
  );

  const value = useMemo(
    () => ({ hydrated, cases, createCase, updateCase, deleteCase, resetSample, findRequest }),
    [hydrated, cases, createCase, updateCase, deleteCase, resetSample, findRequest],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside StoreProvider");
  return ctx;
}

export function useCase(id: string | undefined) {
  const store = useStore();
  return { ...store, kase: id ? store.cases[id] : undefined };
}