from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def test_health_is_ok():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_root_redirects_to_docs_in_development():
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/docs"


def test_security_headers_present():
    res = client.get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"


def test_ready_reports_unreachable_database(monkeypatch):
    monkeypatch.setattr(main, "database_is_reachable", lambda: False)
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json()["database"] == "unreachable"


def test_ready_reports_reachable_database(monkeypatch):
    monkeypatch.setattr(main, "database_is_reachable", lambda: True)
    res = client.get("/health/ready")
    assert res.status_code == 200