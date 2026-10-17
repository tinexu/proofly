"""Week 6, Day 2: evidence-request endpoints for the renter and the subletter."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import EvidenceRequest
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in


def new_case(client, outbox) -> str:
    sign_in(client, outbox)
    return create(client).json()["id"]


def make_link(client, case_id, scopes=("person_unit_relationship", "sublet_authorization"), hours=72):
    return client.post(f"/cases/{case_id}/evidence-requests", json={"scopes": list(scopes), "expires_in_hours": hours})


def token_of(link: str) -> str:
    return link.rsplit("/r/", 1)[1]


def lookup(client, token):
    return client.post("/evidence-requests/lookup", json={"token": token})


# --- Creating ------------------------------------------------------------------------

def test_create_returns_the_link_once(client, outbox):
    case_id = new_case(client, outbox)
    res = make_link(client, case_id)
    assert res.status_code == 201
    body = res.json()
    assert body["link"].startswith(f"{get_settings().web_base_url}/r/")
    assert body["status"] == "open"
    assert body["scopes"] == ["person_unit_relationship", "sublet_authorization"]
    listed = client.get(f"/cases/{case_id}/evidence-requests").json()
    assert "link" not in listed[0]  # never shown again


def test_default_expiry_is_3_days(client, outbox):
    case_id = new_case(client, outbox)
    body = client.post(f"/cases/{case_id}/evidence-requests", json={"scopes": ["price_and_term"]}).json()
    lasts = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["created_at"])
    assert lasts == timedelta(hours=72)


@pytest.mark.parametrize("body", [
    {"scopes": []},
    {"scopes": ["ssn"]},
    {"scopes": ["price_and_term"], "expires_in_hours": 48},
    {"scopes": ["price_and_term"], "expires_in_hours": 720},
    {"scopes": ["price_and_term"], "note": "extra field"},
])
def test_bad_requests_rejected(client, outbox, body):
    case_id = new_case(client, outbox)
    assert client.post(f"/cases/{case_id}/evidence-requests", json=body).status_code == 422


def test_repeated_scopes_are_merged(client, outbox):
    case_id = new_case(client, outbox)
    body = make_link(client, case_id, ["price_and_term", "property_existence", "price_and_term"]).json()
    assert body["scopes"] == ["property_existence", "price_and_term"]


def test_creating_shows_in_activity(client, outbox):
    case_id = new_case(client, outbox)
    make_link(client, case_id, hours=24)
    top = client.get(f"/cases/{case_id}/activity").json()[0]
    assert top["description"] == "Created an evidence link asking for 2 items (expires in 24 hours)"


# --- Listing and revoking -------------------------------------------------------------

def test_list_newest_first_with_status(client, outbox):
    case_id = new_case(client, outbox)
    first = make_link(client, case_id).json()["id"]
    second = make_link(client, case_id).json()["id"]
    client.post(f"/cases/{case_id}/evidence-requests/{first}/revoke")
    listed = client.get(f"/cases/{case_id}/evidence-requests").json()
    assert [(r["id"], r["status"]) for r in listed] == [(second, "open"), (first, "revoked")]


def test_revoke_closes_the_link(client, outbox):
    case_id = new_case(client, outbox)
    created = make_link(client, case_id).json()
    res = client.post(f"/cases/{case_id}/evidence-requests/{created['id']}/revoke")
    assert res.status_code == 200 and res.json()["status"] == "revoked"
    assert lookup(client, token_of(created["link"])).status_code == 404


def test_revoke_twice_is_harmless(client, outbox):
    case_id = new_case(client, outbox)
    req_id = make_link(client, case_id).json()["id"]
    first = client.post(f"/cases/{case_id}/evidence-requests/{req_id}/revoke").json()
    second = client.post(f"/cases/{case_id}/evidence-requests/{req_id}/revoke").json()
    assert first["revoked_at"] == second["revoked_at"]


def test_cannot_revoke_a_link_from_another_case(client, outbox):
    case_a = new_case(client, outbox)
    case_b = create(client).json()["id"]
    req_id = make_link(client, case_a).json()["id"]
    res = client.post(f"/cases/{case_b}/evidence-requests/{req_id}/revoke")
    assert res.status_code == 404 and res.json()["detail"] == "Request not found."


def test_revoke_unknown_request_is_404(client, outbox):
    case_id = new_case(client, outbox)
    assert client.post(f"/cases/{case_id}/evidence-requests/{uuid.uuid4()}/revoke").status_code == 404


# --- The subletter's view -------------------------------------------------------------

def test_subletter_sees_only_what_was_asked(client, outbox):
    case_id = new_case(client, outbox)
    created = make_link(client, case_id, ["sublet_authorization", "price_and_term"]).json()
    client.cookies.clear()  # the subletter has no account
    res = lookup(client, token_of(created["link"]))
    assert res.status_code == 200
    body = res.json()
    assert [i["type"] for i in body["items"]] == ["sublet_authorization", "price_and_term"]
    assert body["items"][0]["label"] == "Subletting is allowed"
    assert "written permission" in body["items"][0]["prompt"]
    assert set(body) == {"items", "expires_at"}


def test_subletter_view_reveals_nothing_about_the_renter(client, outbox):
    case_id = new_case(client, outbox)
    created = make_link(client, case_id).json()
    client.cookies.clear()
    text = lookup(client, token_of(created["link"])).text
    for private in ("renter@example.edu", "214 Elm", "Jordan", "Zelle", case_id, "850"):
        assert private not in text


@pytest.mark.parametrize("token", ["x" * 43, "not-a-real-token-at-all-123"])
def test_unknown_link_is_404(client, token):
    res = lookup(client, token)
    assert res.status_code == 404
    assert "isn't valid or has expired" in res.json()["detail"]


def test_expired_link_is_404(client, db, outbox):
    case_id = new_case(client, outbox)
    created = make_link(client, case_id, hours=24).json()
    req = db.scalar(select(EvidenceRequest))
    req.created_at = datetime.now(timezone.utc) - timedelta(hours=30)
    req.expires_at = datetime.now(timezone.utc) - timedelta(hours=6)
    db.commit()
    assert lookup(client, token_of(created["link"])).status_code == 404


def test_link_to_deleted_case_is_404(client, outbox):
    case_id = new_case(client, outbox)
    created = make_link(client, case_id).json()
    client.delete(f"/cases/{case_id}")
    assert lookup(client, token_of(created["link"])).status_code == 404


def test_all_closed_links_look_the_same(client, db, outbox):
    case_id = new_case(client, outbox)
    revoked = make_link(client, case_id).json()
    client.post(f"/cases/{case_id}/evidence-requests/{revoked['id']}/revoke")
    answers = {lookup(client, token_of(revoked["link"])).text, lookup(client, "y" * 43).text}
    assert len(answers) == 1


def test_lookup_token_is_not_in_the_url(client, outbox):
    """Tokens go in the body so they don't end up in server access logs."""
    case_id = new_case(client, outbox)
    token = token_of(make_link(client, case_id).json()["link"])
    assert client.get(f"/evidence-requests/{token}").status_code in (404, 405)


def test_lookup_from_another_site_is_blocked(client, outbox):
    case_id = new_case(client, outbox)
    token = token_of(make_link(client, case_id).json()["link"])
    res = client.post("/evidence-requests/lookup", json={"token": token}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403