# Proofly API

FastAPI backend for Proofly. Week 4, Day 1: skeleton, settings, health checks, local Postgres.

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

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- http://localhost:8000/health shows the API is up
- http://localhost:8000/health/ready shows the API can reach Postgres
- http://localhost:8000/docs shows the interactive API docs (development only)

## Test

```bash
pytest
```

## Stop the database

```bash
docker compose down          # keeps data
docker compose down -v       # deletes data too
```