"""Day 9A: saving the renter's decision (S6), and calls from the web app."""

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditEvent
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in


def new_case(client, outbox) -> str:
    sign_in(client, outbox)
    return create(client).json()["id"]


def decide(client, case_id, decision="pause", note=None):
    return client.put(f"/cases/{case_id}/decision", json={"decision": decision, "decision_note": note})


def test_decision_requires_sign_in(client):
    assert decide(client, uuid.uuid4()).status_code == 401


def test_save_decision_and_note(client, outbox):
    case_id = new_case(client, outbox)
    res = decide(client, case_id, "proceed_independent", "Called the office on Elm St")
    assert res.status_code == 200
    assert res.json()["decision"] == "proceed_independent"
    assert res.json()["decision_note"] == "Called the office on Elm St"
    assert client.get(f"/cases/{case_id}").json()["decision"] == "proceed_independent"


def test_clear_decision(client, outbox):
    case_id = new_case(client, outbox)
    decide(client, case_id, "stop", "No")
    body = decide(client, case_id, None, "").json()
    assert body["decision"] is None and body["decision_note"] is None


@pytest.mark.parametrize("decision", ["go", "safe", "PAUSE"])
def test_unknown_decision_rejected(client, outbox, decision):
    case_id = new_case(client, outbox)
    assert decide(client, case_id, decision).status_code == 422


def test_note_length_limit(client, outbox):
    case_id = new_case(client, outbox)
    assert decide(client, case_id, "pause", "x" * 1001).status_code == 422


def test_other_user_cannot_decide(client, outbox):
    case_id = new_case(client, outbox)
    as_other_user(client, outbox)
    assert decide(client, case_id).status_code == 404


def test_decision_audited_without_the_note(client, db, outbox):
    case_id = new_case(client, outbox)
    decide(client, case_id, "stop", "Private reason")
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "case.decision_recorded"))
    assert event.detail == {"decision": "stop"}
    activity = client.get(f"/cases/{case_id}/activity").json()
    assert activity[0]["description"] == "Recorded a decision: stop"
    assert "Private reason" not in str(activity)


# --- The web app at localhost:3000 can call the API with its cookie -------------------

def test_cors_preflight_allows_the_web_app(client):
    origin = get_settings().cors_origin_list[0]
    res = client.options(
        "/cases",
        headers={"Origin": origin, "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == origin
    assert res.headers["access-control-allow-credentials"] == "true"
    assert "PUT" in res.headers["access-control-allow-methods"]


def test_cors_rejects_other_sites(client):
    res = client.options(
        "/cases", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in res.headers