# Proofly

Check a sublet before you pay. Proofly shows each claim about a sublet offer with the
evidence behind it and what's still unknown. It never declares a listing safe.

| Folder | What | Details |
|---|---|---|
| `api/` | FastAPI backend + Postgres | [api/README.md](api/README.md) |
| `web/` | Next.js website | [web/README.md](web/README.md) |
| `.github/workflows/ci.yml` | Runs all tests and builds on every push | |

## Run everything locally

Needs Docker Desktop (running), Python 3.12+, and Node 20.9+.

**Terminal 1: API** (first time: see api/README.md for setup)

```bash
cd api
source .venv/bin/activate
docker compose up -d                 # Postgres
python -m alembic upgrade head       # create/update tables
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2: website** (first time: `npm install`)

```bash
cd web
npm run dev
```

Open **http://localhost:3000** (use `localhost`, not `127.0.0.1`, so the sign-in cookie works).
Sign-in emails print in Terminal 1.

## Check everything

```bash
cd api && python -m pytest                                   # API tests
cd web && npm run typecheck && npm run check:copy && npm run build
```

CI runs the same checks on GitHub for every push.

## Where the project is

Built so far (spec weeks 3–5): clickable screens S1–S6, email sign-in, cases, claim
reviews with provenance, decisions, an append-only audit log, deletion with a purge
job, and access checks on every case endpoint.

Next (week 6): evidence requests and uploads.