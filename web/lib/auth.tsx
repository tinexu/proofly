"use client";

// Who is signed in (Week 4, Day 9). Replaces the prototype's in-browser store.

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, api, type ApiUser } from "./api";

interface AuthValue {
  /** undefined = still checking, null = signed out */
  user: ApiUser | null | undefined;
  /** Problem reaching the API, if any (shown instead of pretending you're signed out). */
  error: string | null;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ApiUser | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setUser(null);
        setError(null);
      } else {
        setUser(null);
        setError(e instanceof Error ? e.message : "Can't reach the Proofly API.");
      }
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* already signed out */
    }
    setUser(null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <AuthContext.Provider value={{ user, error, refresh, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Renders children only when signed in; otherwise sends you to sign in and back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, error } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (user === null && !error) {
      const next = pathname + (typeof window !== "undefined" ? window.location.search : "");
      router.replace(`/signin?next=${encodeURIComponent(next)}`);
    }
  }, [user, error, pathname, router]);

  if (error) return <div className="notice notice-caution" role="alert"><strong>Can't load this page</strong><div>{error}</div></div>;
  if (!user) return <p className="muted">Checking sign-in…</p>;
  return <>{children}</>;
}

/** Only allow redirects to our own pages, never to another site. */
export function safeNext(next: string | null, fallback = "/cases"): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}