"""Proofly API entry point.

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs  (turned off in production)
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app import auth, cases, claims
from app.config import get_settings
from app.db import database_is_reachable

settings = get_settings()

app = FastAPI(
    title="Proofly API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(claims.router)


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_foreign_origins(request: Request, call_next) -> Response:
    """Extra protection for the session cookie: a page on another site can't change data.

    Browsers send an Origin header on cross-site requests. Requests without one
    (curl, tests, the API docs on the same origin) are allowed.
    """
    origin = request.headers.get("origin")
    allowed = set(settings.cors_origin_list) | {str(request.base_url).rstrip("/")}
    if request.method in UNSAFE_METHODS and origin and origin not in allowed:
        return JSONResponse({"detail": "Request blocked: unexpected origin."}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False, response_model=None)
def root() -> RedirectResponse | dict[str, str]:
    """In development, send visitors to the docs. In production, just name the service."""
    if settings.is_production:
        return {"service": "proofly-api"}
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: the process is up. Doesn't touch the database."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready() -> JSONResponse:
    """Readiness: the API can reach Postgres."""
    if database_is_reachable():
        return JSONResponse({"status": "ok", "database": "reachable"})
    return JSONResponse({"status": "unavailable", "database": "unreachable"}, status_code=503)