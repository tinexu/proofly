"use client";

// S2 / Offer details. Works fully by manual entry (F01): no scraper or AI involved.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import type { ClaimedRole, Offer, PermissionClaim, Platform } from "@/lib/types";
import { PERMISSION_LABEL, PLATFORM_LABEL, ROLE_LABEL } from "@/lib/content";
import { api } from "@/lib/api";
import { RequireAuth } from "@/lib/auth";

function platformFromUrl(url: string): Platform | null {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (/facebook\.com|fb\.com/.test(host)) return "facebook";
    if (/instagram\.com/.test(host)) return "instagram";
    if (/reddit\.com/.test(host)) return "reddit";
    if (/discord\.(com|gg)/.test(host)) return "discord";
    return "other";
  } catch {
    return null;
  }
}

function OfferForm() {
  const params = useSearchParams();
  const router = useRouter();
  const sourceUrl = params.get("url") ?? "";
  const suggested = useMemo(() => (sourceUrl ? platformFromUrl(sourceUrl) : null), [sourceUrl]);

  const [offer, setOffer] = useState<Offer>({
    address: "",
    startDate: "",
    endDate: "",
    monthlyRent: "",
    deposit: "",
    platform: suggested ?? "facebook",
    platformSuggested: !!suggested,
    sourceUrl,
    claimedRole: "not_stated",
    contactHandle: "",
    permissionClaim: "not_mentioned",
    paymentMethod: "",
  });
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof Offer>(key: K, value: Offer[K]) =>
    setOffer((o) => ({ ...o, [key]: value, ...(key === "platform" ? { platformSuggested: false } : {}) }));

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const problems: string[] = [];
    if (!offer.address.trim()) problems.push("Add the address, even if it's approximate.");
    if (!offer.monthlyRent.trim() && !(offer.startDate && offer.endDate))
      problems.push("Add the monthly rent or the move-in and move-out dates.");
    if (offer.startDate && offer.endDate && offer.endDate < offer.startDate)
      problems.push("The move-out date is before the move-in date.");
    setErrors(problems);
    if (problems.length) return;
    setBusy(true);
    try {
      const created = await api.createCase({ ...offer, platformSuggested: false });
      router.push(`/case/${created.id}`);
    } catch (err) {
      setErrors([err instanceof Error ? err.message : "Couldn't save the case."]);
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={onSubmit} noValidate>
      <div>
        <p className="eyebrow">Step 1 of 2</p>
        <h1>What was offered?</h1>
        <p className="lead">Enter what the listing or the person told you. You can change anything later.</p>
      </div>

      {errors.length > 0 && (
        <div className="notice notice-caution" role="alert">
          <strong>A few things to fix</strong>
          <ul>{errors.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}

      <fieldset className="card stack">
        <legend>The place</legend>
        <label htmlFor="address">Address and unit</label>
        <input id="address" autoComplete="off" value={offer.address} onChange={(e) => set("address", e.target.value)} placeholder="e.g. 214 Elm Street, Unit 3B" />
        <div className="grid2">
          <div><label htmlFor="start">Move-in</label><input id="start" type="date" value={offer.startDate} onChange={(e) => set("startDate", e.target.value)} /></div>
          <div><label htmlFor="end">Move-out</label><input id="end" type="date" value={offer.endDate} onChange={(e) => set("endDate", e.target.value)} /></div>
          <div><label htmlFor="rent">Monthly rent ($)</label><input id="rent" inputMode="decimal" value={offer.monthlyRent} onChange={(e) => set("monthlyRent", e.target.value.replace(/[^\d.]/g, ""))} /></div>
          <div><label htmlFor="deposit">Deposit ($)</label><input id="deposit" inputMode="decimal" value={offer.deposit} onChange={(e) => set("deposit", e.target.value.replace(/[^\d.]/g, ""))} /></div>
        </div>
      </fieldset>

      <fieldset className="card stack">
        <legend>Where you found it and who posted it</legend>
        <label htmlFor="platform">Platform</label>
        <select id="platform" value={offer.platform} onChange={(e) => set("platform", e.target.value as Platform)} aria-describedby={offer.platformSuggested ? "platform-hint" : undefined}>
          {Object.entries(PLATFORM_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {offer.platformSuggested && <p id="platform-hint" className="hint small">Guessed from your link. Please confirm.</p>}
        <label htmlFor="role">What did they say their role is?</label>
        <select id="role" value={offer.claimedRole} onChange={(e) => set("claimedRole", e.target.value as ClaimedRole)}>
          {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label htmlFor="contact">How you're talking to them (name or handle, optional)</label>
        <input id="contact" value={offer.contactHandle} onChange={(e) => set("contactHandle", e.target.value)} placeholder="e.g. Jordan on Messenger" />
        <label htmlFor="permission">Did they say the landlord allows subletting?</label>
        <select id="permission" value={offer.permissionClaim} onChange={(e) => set("permissionClaim", e.target.value as PermissionClaim)}>
          {Object.entries(PERMISSION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label htmlFor="payment">How did they ask to be paid? (optional)</label>
        <input id="payment" value={offer.paymentMethod} onChange={(e) => set("paymentMethod", e.target.value)} placeholder="e.g. Zelle deposit before the tour" />
      </fieldset>

      <div className="row">
        <button type="submit" className="button" disabled={busy}>{busy ? "Saving…" : "Create my checklist"}</button>
      </div>
    </form>
  );
}

export default function NewCasePage() {
  return (
    <RequireAuth>
      <Suspense fallback={<p className="muted">Loading…</p>}>
        <OfferForm />
      </Suspense>
    </RequireAuth>
  );
}