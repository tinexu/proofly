"""Week 6, Day 4: virus scanning and downloading clean files."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Evidence
from app.scan import scan_pending, selftest
from tests.test_cases import as_other_user
from tests.test_uploads import PDF, PNG, setup_link, submit

EVIL_PDF = b"%PDF-1.7 EVIL payload"


def evidence(db, case_id) -> list[Evidence]:
    db.expire_all()
    return list(db.scalars(select(Evidence).where(Evidence.case_id == uuid.UUID(case_id)).order_by(Evidence.original_name)))


# --- Scanning right after upload -----------------------------------------------------

def test_clean_files_unlock_right_away(client, db, outbox, scanner):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("person_unit_relationship", "b.png", PNG)])
    assert [e.status for e in evidence(db, case_id)] == ["clean", "clean"]
    assert all(e.scanned_at is not None for e in evidence(db, case_id))
    assert scanner.scanned == 2


def test_infected_file_is_blocked_and_deleted(client, db, outbox, storage):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("person_unit_relationship", "evil.pdf", EVIL_PDF)])
    rows = {e.original_name: e for e in evidence(db, case_id)}
    assert rows["a.pdf"].status == "clean"
    assert rows["evil.pdf"].status == "infected"
    assert rows["evil.pdf"].storage_key not in storage.files  # deleted at once
    assert rows["a.pdf"].storage_key in storage.files


def test_scanner_down_keeps_files_locked_but_upload_succeeds(client, db, outbox, scanner):
    case_id, token = setup_link(client, outbox)
    scanner.up = False
    res = submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    assert res.status_code == 201
    assert [e.status for e in evidence(db, case_id)] == ["pending_scan"]


def test_retry_job_scans_what_was_left(client, db, outbox, storage, scanner):
    case_id, token = setup_link(client, outbox)
    scanner.up = False
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    scanner.up = True
    summary = scan_pending(db, storage, scanner)
    assert (summary.clean, summary.infected, summary.errors) == (1, 0, 0)
    assert [e.status for e in evidence(db, case_id)] == ["clean"]


def test_scan_errors_stay_locked_and_are_retried(client, db, outbox, storage, scanner):
    case_id, token = setup_link(client, outbox)
    scanner.fail = True
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    assert [e.status for e in evidence(db, case_id)] == ["scan_error"]
    scanner.fail = False
    scan_pending(db, storage, scanner)
    assert [e.status for e in evidence(db, case_id)] == ["clean"]


def test_job_skips_everything_when_scanner_unreachable(client, db, outbox, storage, scanner):
    case_id, token = setup_link(client, outbox)
    scanner.up = False
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    summary = scan_pending(db, storage, scanner)
    assert summary.skipped and scanner.scanned == 0


def test_deleted_cases_are_not_scanned(client, db, outbox, storage, scanner):
    case_id, token = setup_link(client, outbox)
    scanner.up = False
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    client.delete(f"/cases/{case_id}")
    scanner.up = True
    scan_pending(db, storage, scanner)
    assert scanner.scanned == 0


def test_scan_result_in_activity(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF), ("person_unit_relationship", "evil.pdf", EVIL_PDF)])
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence.scanned"))
    assert event.actor_type == "system"
    assert event.detail == {"clean_count": 1, "infected_count": 1}
    top = client.get(f"/cases/{case_id}/activity").json()[0]
    assert top["description"] == "Virus check finished: 1 clean, 1 blocked as unsafe and deleted"


# --- Downloading ----------------------------------------------------------------------

def file_url(case_id, evidence_id):
    return f"/cases/{case_id}/evidence/{evidence_id}/file"


def test_download_clean_file(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "lease page 1.pdf", PDF)])
    ev = evidence(db, case_id)[0]
    res = client.get(file_url(case_id, ev.id))
    assert res.status_code == 200
    assert res.content == PDF
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"] == 'attachment; filename="lease page 1.pdf"'
    assert "sandbox" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("setup,expected", [
    ("down", "still being checked"),
    ("fail", "couldn't be checked"),
    ("evil", "blocked by the virus check"),
])
def test_locked_files_cannot_be_downloaded(client, db, outbox, scanner, setup, expected):
    case_id, token = setup_link(client, outbox)
    scanner.up = setup != "down"
    scanner.fail = setup == "fail"
    submit(client, token, [("sublet_authorization", "a.pdf", EVIL_PDF if setup == "evil" else PDF)])
    ev = evidence(db, case_id)[0]
    res = client.get(file_url(case_id, ev.id))
    assert res.status_code == 423
    assert expected in res.json()["detail"]


def test_file_from_another_case_is_404(client, db, outbox):
    case_a, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    ev = evidence(db, case_a)[0]
    case_b = client.post("/cases", json={"address": "Other", "monthly_rent": "1"}).json()["id"]
    res = client.get(file_url(case_b, ev.id))
    assert res.status_code == 404 and res.json()["detail"] == "File not found."


def test_stranger_cannot_download(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    ev = evidence(db, case_id)[0]
    as_other_user(client, outbox)
    assert client.get(file_url(case_id, ev.id)).status_code == 404


def test_subletter_cannot_download(client, db, outbox):
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("sublet_authorization", "a.pdf", PDF)])
    ev = evidence(db, case_id)[0]
    client.cookies.clear()
    assert client.get(file_url(case_id, ev.id)).status_code == 401


# --- Self-test --------------------------------------------------------------------------

def test_selftest_with_working_scanner(scanner, capsys):
    class EicarAware(type(scanner)):
        def scan(self, data):
            from app.scanner import EICAR, ScanResult
            return ScanResult("infected", "Eicar-Test-Signature") if data == EICAR else ScanResult("clean")

    assert selftest(EicarAware()) is True
    assert "Scanner works." in capsys.readouterr().out


def test_selftest_with_scanner_down(scanner, capsys):
    scanner.up = False
    assert selftest(scanner) is False
    assert "not reachable" in capsys.readouterr().out