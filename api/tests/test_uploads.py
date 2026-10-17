"""Week 6, Day 3: the subletter uploads files through their link."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Case, Claim, Evidence, EvidenceRequest
from app.purge import purge
from app.uploads import MAX_FILE_BYTES, clean_name, detect_type
from tests.test_cases import as_other_user, create
from tests.test_sessions import sign_in

PDF = b"%PDF-1.7\n" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 200
JPG = b"\xff\xd8\xff\xe0" + b"x" * 200


def setup_link(client, outbox, scopes=("person_unit_relationship", "sublet_authorization")):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    res = client.post(f"/cases/{case_id}/evidence-requests", json={"scopes": list(scopes)})
    token = res.json()["link"].rsplit("/r/", 1)[1]
    return case_id, token


def submit(client, token, files, consent="true"):
    """files: list of (claim_type, filename, bytes)."""
    data = {"token": token}
    if consent is not None:
        data["consent"] = consent
    return client.post(
        "/evidence-requests/submit",
        data=data,
        files=[(claim, (name, content, "application/octet-stream")) for claim, name, content in files],
    )


# --- File checks (no HTTP) ---------------------------------------------------------

@pytest.mark.parametrize("data,kind", [
    (PDF, "application/pdf"), (PNG, "image/png"), (JPG, "image/jpeg"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    (b"\x00\x00\x00\x18ftypheic\x00\x00", "image/heic"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'/>", None),
    (b"<html><script>alert(1)</script>", None),
    (b"MZ\x90\x00 windows program", None),
    (b"PK\x03\x04 zip or docx", None),
    (b"", None),
])
def test_detect_type_from_contents(data, kind):
    assert detect_type(data) == kind


@pytest.mark.parametrize("raw,clean", [
    ("lease.pdf", "lease.pdf"),
    ("../../etc/passwd", "passwd"),
    ("C:\\Users\\me\\lease page 1.pdf", "lease page 1.pdf"),
    ("<script>.pdf", "_script_.pdf"),
    ("", "file"),
    ("a" * 300 + ".pdf", "a" * 100),
])
def test_clean_name(raw, clean):
    assert clean_name(raw) == clean


# --- Happy path ------------------------------------------------------------------------

def test_upload_files(client, db, outbox, storage):
    case_id, token = setup_link(client, outbox)
    client.cookies.clear()  # the subletter has no account
    res = submit(client, token, [
        ("person_unit_relationship", "lease-page-1.pdf", PDF),
        ("sublet_authorization", "permission.png", PNG),
    ])
    assert res.status_code == 201
    assert res.json()["received"] == 2

    rows = db.scalars(select(Evidence).where(Evidence.case_id == uuid.UUID(case_id))).all()
    assert {(r.claim_type, r.original_name, r.content_type, r.status) for r in rows} == {
        ("person_unit_relationship", "lease-page-1.pdf", "application/pdf", "clean"),  # scanned right away (Day 4)
        ("sublet_authorization", "permission.png", "image/png", "clean"),
    }
    assert {storage.get(r.storage_key) for r in rows} == {PDF, PNG}
    assert all(len(r.sha256) == 64 and r.size_bytes > 0 for r in rows)


def test_link_closes_after_one_reply(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    assert submit(client, token, [("sublet_authorization", "a.pdf", PDF)]).status_code == 201
    again = submit(client, token, [("sublet_authorization", "b.pdf", PDF)])
    assert again.status_code == 404
    assert client.post("/evidence-requests/lookup", json={"token": token}).status_code == 404
    req = db.scalar(select(EvidenceRequest))
    assert req.responded_at is not None


def test_claims_move_to_evidence_received(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    states = {c.type: c.state for c in db.scalars(select(Claim).where(Claim.case_id == uuid.UUID(case_id)))}
    assert states["sublet_authorization"] == "EVIDENCE_SUBMITTED"
    assert states["person_unit_relationship"] == "UNCHECKED"  # asked for but nothing sent


def test_hand_reviewed_claims_are_left_alone(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    client.patch(f"/cases/{case_id}/claims/sublet_authorization", json={"state": "CONFLICTING", "rationale": "Landlord said no"})
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    claim = db.scalar(select(Claim).where(Claim.case_id == uuid.UUID(case_id), Claim.type == "sublet_authorization"))
    assert claim.state == "CONFLICTING" and claim.reviewer == "user"


def test_reply_shows_in_activity_as_the_subletter(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("sublet_authorization", "b.png", PNG)])
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence.received"))
    assert event.actor_type == "subletter" and event.actor_user_id is None
    assert event.detail == {"file_count": 2}
    received = client.get(f"/cases/{case_id}/activity").json()[1]  # [0] is the virus-check result (Day 4)
    assert received["actor"] == "subletter"
    assert received["description"] == "The subletter sent 2 files (locked until checked for viruses)"


# --- Renter's list of files -------------------------------------------------------

def test_renter_lists_files_without_storage_details(client, outbox, scanner):
    scanner.up = False  # keep it locked so we see the pending status
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "permission.pdf", PDF)])
    files = client.get(f"/cases/{case_id}/evidence").json()
    assert len(files) == 1
    assert files[0]["original_name"] == "permission.pdf"
    assert files[0]["status"] == "pending_scan"
    assert "storage_key" not in files[0] and "sha256" not in files[0]


def test_stranger_cannot_list_files(client, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    as_other_user(client, outbox)
    assert client.get(f"/cases/{case_id}/evidence").status_code == 404


# --- Rejections ----------------------------------------------------------------------------

def test_consent_required(client, outbox, storage):
    _, token = setup_link(client, outbox)
    for consent in (None, "false", ""):
        res = submit(client, token, [("sublet_authorization", "a.pdf", PDF)], consent=consent)
        assert res.status_code == 422 and "confirm" in res.json()["detail"]
    assert storage.files == {}


def test_no_files(client, outbox):
    _, token = setup_link(client, outbox)
    res = client.post("/evidence-requests/submit", data={"token": token, "consent": "true"})
    assert res.status_code == 422 and "at least one file" in res.json()["detail"]


def test_file_for_something_not_asked(client, outbox, storage):
    _, token = setup_link(client, outbox, scopes=["sublet_authorization"])
    res = submit(client, token, [("payment_destination", "a.pdf", PDF)])
    assert res.status_code == 422 and "didn't ask for" in res.json()["detail"]
    assert storage.files == {}


@pytest.mark.parametrize("name,content", [
    ("lease.pdf", b"<html><script>alert(1)</script></html>"),
    ("photo.png", b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>"),
    ("lease.pdf", b"MZ\x90\x00 a windows program"),
    ("lease.docx", b"PK\x03\x04 a word file"),
])
def test_wrong_file_types_rejected_whatever_the_name(client, outbox, storage, name, content):
    _, token = setup_link(client, outbox)
    res = submit(client, token, [("sublet_authorization", name, content)])
    assert res.status_code == 415
    assert storage.files == {}


def test_too_large(client, outbox, storage):
    _, token = setup_link(client, outbox)
    big = b"%PDF-" + b"x" * MAX_FILE_BYTES
    res = submit(client, token, [("sublet_authorization", "big.pdf", big)])
    assert res.status_code == 413
    assert storage.files == {}


def test_empty_file(client, outbox):
    _, token = setup_link(client, outbox)
    assert submit(client, token, [("sublet_authorization", "empty.pdf", b"")]).status_code == 422


def test_too_many_per_item(client, outbox):
    _, token = setup_link(client, outbox)
    res = submit(client, token, [("sublet_authorization", f"{i}.pdf", PDF) for i in range(4)])
    assert res.status_code == 422 and "per item" in res.json()["detail"]


def test_too_many_in_total(client, outbox):
    _, token = setup_link(client, outbox, scopes=["property_existence", "person_unit_relationship", "sublet_authorization", "price_and_term"])
    files = [(t, f"{i}.pdf", PDF) for t in ("property_existence", "person_unit_relationship", "sublet_authorization", "price_and_term") for i in range(3)]
    assert submit(client, token, files).status_code in (400, 422)


def test_one_bad_file_rejects_the_whole_reply(client, db, outbox, storage):
    _, token = setup_link(client, outbox)
    res = submit(client, token, [("sublet_authorization", "ok.pdf", PDF), ("sublet_authorization", "bad.pdf", b"nope")])
    assert res.status_code == 415
    assert storage.files == {}
    assert db.scalar(select(EvidenceRequest)).responded_at is None  # link still open to try again


# --- Closed links --------------------------------------------------------------------------

@pytest.mark.parametrize("token", ["x" * 43, "not-a-real-token-at-all-123"])
def test_unknown_link(client, token):
    res = submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    assert res.status_code == 404


def test_missing_token(client):
    res = client.post("/evidence-requests/submit", data={"consent": "true"}, files=[("sublet_authorization", ("a.pdf", PDF))])
    assert res.status_code == 404


def test_revoked_link(client, outbox):
    case_id, token = setup_link(client, outbox)
    req_id = client.get(f"/cases/{case_id}/evidence-requests").json()[0]["id"]
    client.post(f"/cases/{case_id}/evidence-requests/{req_id}/revoke")
    assert submit(client, token, [("sublet_authorization", "a.pdf", PDF)]).status_code == 404


def test_expired_link(client, db, outbox):
    _, token = setup_link(client, outbox)
    req = db.scalar(select(EvidenceRequest))
    req.created_at = datetime.now(timezone.utc) - timedelta(days=4)
    req.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert submit(client, token, [("sublet_authorization", "a.pdf", PDF)]).status_code == 404


def test_deleted_case(client, outbox):
    case_id, token = setup_link(client, outbox)
    client.delete(f"/cases/{case_id}")
    assert submit(client, token, [("sublet_authorization", "a.pdf", PDF)]).status_code == 404


# --- Storage failures and purging -------------------------------------------------

def test_storage_failure_saves_nothing_and_keeps_link_open(client, db, outbox, storage):
    _, token = setup_link(client, outbox)
    storage.fail_after = 1  # first file stores, second fails
    res = submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("person_unit_relationship", "b.pdf", PDF)])
    assert res.status_code == 503 and "try again" in res.json()["detail"]
    assert storage.files == {}  # the first file was cleaned up
    db.expire_all()
    assert db.scalars(select(Evidence)).all() == []
    assert db.scalar(select(EvidenceRequest)).responded_at is None


def test_purge_deletes_the_files(client, db, outbox, storage):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("person_unit_relationship", "b.png", PNG)])
    assert len(storage.files) == 2
    client.delete(f"/cases/{case_id}")
    result = purge(db, now=datetime.now(timezone.utc) + timedelta(days=2), storage=storage)
    assert (result.cases, result.files) == (1, 2)
    assert storage.files == {}
    assert db.get(Case, uuid.UUID(case_id)) is None


def test_purge_retries_later_if_storage_fails(client, db, outbox, storage):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    client.delete(f"/cases/{case_id}")

    class Broken:
        def delete(self, key):
            raise RuntimeError("storage down")

    result = purge(db, now=datetime.now(timezone.utc) + timedelta(days=2), storage=Broken())
    assert result.cases == 0
    assert db.get(Case, uuid.UUID(case_id)) is not None  # still there for the next run