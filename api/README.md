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

## Evidence files

Files the subletter sends are checked (type from the file's contents, 10 MB max,
3 per item, 10 in total), stored under a random name in private storage, and
start **locked** (`pending_scan`). Nobody can download them until a virus scan
marks them clean (Week 6, Day 4).

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