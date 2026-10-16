"""Day 10: one table that checks access rules on every case endpoint.

For each endpoint that takes a case ID:
- signed out           → 401
- someone else's case  → 404 (same as a case that doesn't exist)
- a deleted case       → 404, even for the owner
- the owner            → succeeds

`test_every_case_endpoint_is_covered` fails if a new endpoint is added without
being listed here, so access checks can't be forgotten.
"""

import uuid

import pytest

from app.main import app
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in

# (method, path, JSON body, expected success status)
CASE_ENDPOINTS = [
    ("GET", "/cases/{case_id}", None, 200),
    ("GET", "/cases/{case_id}/activity", None, 200),
    ("PUT", "/cases/{case_id}/decision", {"decision": "pause", "decision_note": None}, 200),
    ("PATCH", "/cases/{case_id}/claims/{claim_type}", {"state": "CONFLICTING", "rationale": "Rent differs"}, 200),
    ("DELETE", "/cases/{case_id}/claims/{claim_type}/review", None, 200),
    ("DELETE", "/cases/{case_id}", None, 204),
]
IDS = [f"{m} {p}" for m, p, _, _ in CASE_ENDPOINTS]


def call(client, method, path, body, case_id):
    url = path.format(case_id=case_id, claim_type="price_and_term")
    return client.request(method, url, json=body)


def test_every_case_endpoint_is_covered():
    # The OpenAPI schema lists every endpoint the app serves (the same list /docs shows).
    in_app = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if "{case_id}" in path
        for method in operations
    }
    in_table = {(m, p) for m, p, _, _ in CASE_ENDPOINTS}
    assert in_app == in_table, f"Add these to CASE_ENDPOINTS: {in_app - in_table}"


@pytest.mark.parametrize("method,path,body,ok", CASE_ENDPOINTS, ids=IDS)
def test_signed_out_gets_401(client, method, path, body, ok):
    assert call(client, method, path, body, uuid.uuid4()).status_code == 401


@pytest.mark.parametrize("method,path,body,ok", CASE_ENDPOINTS, ids=IDS)
def test_stranger_gets_404(client, outbox, method, path, body, ok):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    as_other_user(client, outbox)
    res = call(client, method, path, body, case_id)
    assert res.status_code == 404
    assert res.json() == {"detail": "Case not found."}


@pytest.mark.parametrize("method,path,body,ok", CASE_ENDPOINTS, ids=IDS)
def test_unknown_case_gets_the_same_404(client, outbox, method, path, body, ok):
    sign_in(client, outbox)
    res = call(client, method, path, body, uuid.uuid4())
    assert res.status_code == 404
    assert res.json() == {"detail": "Case not found."}


@pytest.mark.parametrize("method,path,body,ok", CASE_ENDPOINTS, ids=IDS)
def test_deleted_case_gets_404_even_for_owner(client, outbox, method, path, body, ok):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    assert client.delete(f"/cases/{case_id}").status_code == 204
    assert call(client, method, path, body, case_id).status_code == 404


@pytest.mark.parametrize("method,path,body,ok", CASE_ENDPOINTS, ids=IDS)
def test_owner_succeeds(client, outbox, method, path, body, ok):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    assert call(client, method, path, body, case_id).status_code == ok


@pytest.mark.parametrize("method,path", [("GET", "/cases"), ("POST", "/cases")])
def test_case_collection_requires_sign_in(client, method, path):
    assert client.request(method, path, json={"address": "x", "monthly_rent": "1"}).status_code == 401