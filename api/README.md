# Proofly API

FastAPI backend for Proofly.

- Week 4, Day 1: skeleton, settings, health checks, local Postgres
- Week 4, Day 2: database tables (users, cases, claims, audit events) and the first migration
- Week 4, Day 3: email magic-link sign-in (emails print to the terminal in development)
- Week 4, Day 4: sessions (stay signed in), `/auth/me`, sign-out, owner-only case access
- Week 4, Day 5: `POST /cases`, `GET /cases`, `GET /cases/{id}` (signed in, your own cases only)
- Week 4, Day 6: review a claim (`PATCH /cases/{id}/claims/{type}`) with a reason, and undo it (`DELETE …/review`)
- Week 4, Day 7: append-only audit log, and `GET /cases/{id}/activity` to read a case's history
- Week 4, Day 8: `DELETE /cases/{id}` and the purge job (`python -m app.purge`)
- Week 4, Day 9: `PUT /cases/{id}/decision`
- Week 4, Day 10: access tests for every case endpoint
- Week 6, Day 1: evidence-request rules and table (`app/evidence_requests.py`)
- Week 6, Day 2: evidence-link endpoints for the renter, and `POST /evidence-requests/lookup` for the subletter
- Week 6, Day 3: file uploads through a link (`POST /evidence-requests/submit`), private storage, `GET /cases/{id}/evidence`
- Week 6, Day 4: virus scanning with ClamAV, and downloading clean files (`GET /cases/{id}/evidence/{evidence_id}/file`)
- Week 6, Day 5: evidence list includes `request_id` (which link a file came through), for the website
- Week 7, Day 1: rules engine (`app/rules.py`): payment flag, evidence received, undo hands back to the rules
- Week 7, Day 2: "supported" reviews name a clean file from the case (`evidence_id`), enforced in the database too (migration 0007)
- Week 7, Day 3: facts from files (`/cases/{id}/facts`) compared with the listing; a difference marks the claim conflicting (migration 0008)
- Week 7, Day 4: `GET /cases/{id}/export`: the case summary as a Markdown download (`?include_notes=false` for a copy to share)

## Audit log

Every change is recorded through `app/audit.py`'s `record()`, in the same database
transaction as the change itself. `record()` only accepts short codes for a fixed
set of detail keys, so addresses, emails and notes can't end up in the log.
The database refuses to edit or delete audit rows (migration 0004).

## Signing in (development)

1. `POST /auth/magic-link` with `{"email": "you@example.edu"}`. The email, including the link, prints in the terminal running uvicorn.
2. Copy the `token=` value from that link and `POST /auth/verify` with `{"token": "..."}`.

3. Verifying sets an HttpOnly `proofly_session` cookie that lasts 14 days. `GET /auth/me` shows who's signed in, and `POST /auth/logout` signs that browser out.

Links work once and expire after 15 minutes.

Requests that change data (POST, PATCH, DELETE) from another website are blocked by an Origin check.

## First-time setup

Needs Python 3.12+ and Docker Desktop.

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d               # starts Postgres on localhost:5432
```

## Database migrations

Create or update the tables in your dev database:

```bash
python -m alembic upgrade head
```

After changing `app/models.py`, generate a new migration, then read it before committing:

```bash
python -m alembic revision --autogenerate -m "short description"
```

## Run

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000 redirects to the docs (development only)
- http://localhost:8000/health shows the API is up
- http://localhost:8000/health/ready shows the API can reach Postgres
- http://localhost:8000/docs shows the interactive API docs (development only)

## Test

```bash
python -m pytest
```

Database tests use a separate `proofly_test` database, created automatically, so
they never touch your dev data. If Postgres isn't running, they're skipped.

## Stop the database

```bash
docker compose down          # keeps data
docker compose down -v       # deletes data too
```

## Rules engine

`app/rules.py` sets claims the renter hasn't reviewed by hand. Every rule is explicit:

1. a file says something different from the listing (see "Facts" below) → **conflicting**
2. "Where the money goes" + a hard-to-reverse payment method (Zelle, Venmo, Cash App,
   wire, gift cards, crypto) → **needs review**, with a neutral explanation
3. a claim with evidence that wasn't blocked by the virus check → **evidence received**
4. otherwise → **not checked yet**

Rules never mark a claim "supported", and a manual review always wins.
Only the renter can mark a claim supported: `PATCH /cases/{id}/claims/{type}` with
`{"state": "SUPPORTED", "rationale": "...", "evidence_id": "<a clean file from this case>"}`.
Any clean file from the case can be named (a lease page may support more than one
claim). The database refuses a "supported" claim without a file, or set by the rules. Undoing a
review hands the claim back to the rules. Changes show in the activity log as "Proofly marked …".

## Facts: listing vs. files

Proofly doesn't read files. The renter opens one and notes what it says about the
address, move-in/out dates, rent, deposit or payment details:
`PUT /cases/{id}/facts/{field}` with `{"value": "...", "evidence_id": "<a clean file>"}`.
`app/facts.py` compares it with the listing: amounts as amounts ("$1,200" = "1200.00"),
dates as dates, and text after tidying ("Street" = "St", "Apt" = "Unit" = "#"; less
detail isn't a contradiction, a different unit is). The result is `matches`, `differs`
or `listing_silent`. The audit log records which field, never the value. Deleting a
case removes its facts at once.

## Case summary export

`GET /cases/{id}/export` returns a Markdown file built from the database (`app/export.py`):
the offer, each claim with who set it and why, listing vs. files, files received with
SHA-256 fingerprints, what has NOT been verified, how to check independently, the
decision and the activity log. `?include_notes=false` leaves out the renter's notes,
the subletter's contact and the listing link. Typed text is escaped so it can't add
links, images or HTML. Each download is recorded in the activity log.

## Evidence files

Files the subletter sends are checked (type from the file's contents, 10 MB max,
3 per item, 10 in total), stored under a random name in private storage, and
start **locked** (`pending_scan`). They're scanned with ClamAV right after upload:

- **clean** → unlocked; the renter can download it (always as a download, never shown inline)
- **infected** → deleted from storage at once; shown as blocked
- **scanner down or error** → stays locked; `python -m app.scan` retries (run it on a schedule in production)

`docker compose up -d` starts ClamAV next to Postgres. Its first start downloads
virus signatures and can take a few minutes. Check it with:

```bash
python -m app.scan --selftest   # should say: Scanner works.
```

- Development: files go in `api/.storage/` (owner-only permissions, ignored by git).
- Production: `PROOFLY_STORAGE_BACKEND=s3` with `PROOFLY_S3_BUCKET` and the usual
  AWS credentials. Objects are encrypted at rest. Local storage is refused in production.

## Deleting data

`DELETE /cases/{id}` hides the case at once and wipes its personal details
(address, link, contact, payment method, notes). The purge job then removes the
rows and the case's stored files for good once `PROOFLY_CASE_PURGE_DELAY_HOURS` (default 24) have passed. It
also removes sign-in links and sessions that ended more than 7 days ago.

```bash
python -m app.purge --dry-run   # show what would be removed
python -m app.purge             # remove it
```

In production this runs on a schedule (for example hourly). The audit log keeps
a "case.purged" entry, which holds no personal details.