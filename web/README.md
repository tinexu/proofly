# Proofly web

Screens S1–S6 from the Proofly product spec (v0.1), running on the Proofly API (`../api`):
sign-in, cases, claim reviews and decisions (Week 4), and since Week 6, Day 5, evidence:

- **S4** creates scoped, expiring links (shown once), lists them, and revokes them.
- **`/r/<token>`** is the subletter's page: no account, only the items asked for,
  sensitive-data warning, consent, PDF/photo checks before sending.
- **S3/S5** list received files with their virus-check status; clean files download.
- **S5** (Week 7) can mark a claim **Supported** by choosing a clean file and saying what in it
  supports the claim. S3 and S6 show which file, and what that file still can't confirm.
- **S5 "Listing vs. files"** (Week 7): note what a file says about the rent, dates, address,
  deposit or payment; the API compares it with the listing and flags differences.
- **S6 downloads** (Week 7): the case summary comes from the API (`/cases/{id}/export`),
  in full or as a copy to share without your notes.

## Run it

Start the API first (see `../api/README.md`), then:

```bash
cd web
npm install
npm run dev          # http://localhost:3000
npm run typecheck
npm run check:copy   # fails on false-assurance phrases ("verified listing", "safe to pay", …)
npm run build
```

Requires Node 20.9+.

## Screens

| Spec | Route | What to test |
|------|-------|--------------|
| S1 Start | `/` | Do people understand what Proofly does and doesn't do? |
| S2 Offer details | `/case/new` | Manual entry works without any scraper (F01). The platform is guessed from the link and must be confirmed. |
| S3 Case dashboard | `/case/[id]` | Per-claim status, evidence source, timestamp and what's still unknown (F02). There's no overall "safe" score. |
| S4 Request evidence | `/case/[id]/request` | Scoped, expiring, revocable link (F03). "Simulate reply" lets one tester run the whole flow. |
| Subletter view | `/r/[token]` | The uploader sees exactly what was requested, gets sensitive-data warnings, and must consent. File type and size are checked (F04). |
| S5 Compare & review | `/case/[id]/review` | Each mismatch is its own item, and the renter can correct the extraction (F05). A manual review must name its evidence and give a reason. |
| S6 Decision | `/case/[id]/summary` | What's NOT verified, next steps, export (F06), reporting, and deletion (F07). |

Open **the sample case** from S1 to see every status at once: one supported claim, a rent
mismatch ($850 listed vs $950 on the lease), a payment flag, and several unknowns.

## How it's organized

```
web/
  app/                    routes (one folder per screen)
  components/ui.tsx       StatusBadge, ClaimCard, CaseShell (header + step nav)
  lib/types.ts            claim objects + states from spec §08, data model from §10
  lib/rules.ts            pure rules engine: status mapping, discrepancies, payment flags, unknowns
  lib/content.ts          all claim/evidence copy, incl. "supports / does NOT prove" table
  lib/summary.ts          exportable case summary
  lib/store.tsx           prototype-only state (replaced by API calls in Stage 3)
  lib/sample.ts           fictional demo case
  lib/ids.ts              unguessable IDs/tokens
  scripts/check-copy.mjs  false-assurance copy lint
```

`lib/types.ts` and `lib/rules.ts` are written so the FastAPI backend can mirror them.

## Rules the prototype enforces

- **Supported** is set automatically only for an address match from a public record, or a
  manager confirmation through a contact the renter found themselves. Any other evidence
  stays at *Evidence received, not reviewed* until the renter reviews it.
- Any mismatch between a listing field and an evidence field makes that claim **Conflicting**.
- A payment method that's hard to reverse (wire, gift card, crypto, P2P apps) moves the
  payment claim to **Needs your review**, with neutral wording and never an accusation.
- Manual reviews keep their provenance (who, when, why) and can be undone.
- There's no green "all clear" color anywhere. Every status uses a shape plus text, not color alone.

## Not in this stage

Real uploads, auth, the server-side permission model, malware scanning, and extraction.
Those arrive in Stages 3–5.