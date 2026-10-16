"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const router = useRouter();

  async function onSignOut() {
    await signOut();
    router.push("/");
  }

  return (
    <header className="site-header">
      <Link href="/" className="brand">Proofly</Link>
      <nav className="header-nav" aria-label="Account">
        {user ? (
          <>
            <Link href="/cases">My cases</Link>
            <span className="muted small header-email">{user.email}</span>
            <button className="button ghost small-button" onClick={onSignOut}>Sign out</button>
          </>
        ) : user === null ? (
          <Link href="/signin">Sign in</Link>
        ) : null}
      </nav>
    </header>
  );
}