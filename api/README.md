# Proofly API

FastAPI backend for Proofly.

- Week 4, Day 1: skeleton, settings, health checks, local Postgres
- Week 4, Day 2: database tables (users, cases, claims, audit events) and the first migration
- Week 4, Day 3: email magic-link sign-in (emails print to the terminal in development)

## Signing in (development)

1. `POST /auth/magic-link` with `{"email": "you@example.edu"}`. The email, including the link, prints in the terminal running uvicorn.
2. Copy the `token=` value from that link and `POST /auth/verify` with `{"token": "..."}`.

Links work once and expire after 15 minutes. Staying signed in (sessions) arrives on Day 4.

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