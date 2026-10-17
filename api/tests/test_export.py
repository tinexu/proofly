"""Week 7, Day 4: the case summary export."""

from sqlalchemy import select

from app.export import esc
from app.models import AuditEvent
from tests.test_cases import OFFER, as_other_user, create
from tests.test_scanning import EVIL_PDF
from tests.test_sessions import sign_in
from tests.test_uploads import PDF, setup_link, submit


def export(client, case_id, **params):
    return client.get(f"/cases/{case_id}/export", params=params)


def busy_case(client, outbox):
    """A case with a clean file, a blocked file, a supported claim, a mismatch, a note and a decision."""
    case_id, token = setup_link(client, outbox)
    submit(client, token, [("person_unit_relationship", "lease.pdf", PDF), ("sublet_authorization", "evil.pdf", EVIL_PDF)])
    lease = next(f for f in client.get(f"/cases/{case_id}/evidence").json() if f["original_name"] == "lease.pdf")
    client.patch(f"/cases/{case_id}/claims/person_unit_relationship",
                 json={"state": "SUPPORTED", "rationale": "Page 1 names Jordan as tenant", "evidence_id": lease["id"]})
    client.put(f"/cases/{case_id}/facts/monthly_rent", json={"value": "1100", "evidence_id": lease["id"]})
    client.put(f"/cases/{case_id}/decision", json={"decision": "pause", "decision_note": "Waiting on landlord call"})
    return case_id, lease


def test_download_headers(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    res = export(client, case_id)
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/markdown; charset=utf-8"
    assert res.headers["content-disposition"].startswith('attachment; filename="proofly-case-summary-')
    assert res.headers["cache-control"] == "no-store"


def test_full_summary(client, outbox):
    case_id, lease = busy_case(client, outbox)
    text = export(client, case_id).text
    assert text.startswith("# Proofly case summary")
    assert "not a safety guarantee" in text and text.rstrip().endswith("before paying.")
    # offer
    assert "- Address: 214 Elm Street, Unit 3B" in text
    assert "- Monthly rent: $850" in text and "- Dates: Jan 5, 2027 to Apr 30, 2027" in text
    assert "- Contact: Jordan (Messenger)" in text
    # claims
    assert "### This person lives there or controls the lease: Supported" in text
    assert "- Based on the renter's review of: lease.pdf" in text
    assert "- Renter's note: Page 1 names Jordan as tenant" in text
    assert "### Price and dates match: Conflicting" in text
    assert "monthly rent differs from the listing" in text
    assert "### Where the money goes: Needs review" in text
    # listing vs files
    assert "| Monthly rent | $850 | $1,100 | lease.pdf | **Differs** |" in text
    # payment, unknowns, checks
    assert "## Payment" in text and "hard to reverse" in text
    assert "We have not confirmed the landlord or property manager allows this sublet." in text
    assert "## How to check independently" in text
    # files with fingerprints only for clean ones
    assert f"- lease.pdf (for \"This person lives there or controls the lease\"), passed the virus check" in text
    assert "SHA-256: `" in text
    assert "evil.pdf (for \"Subletting is allowed\"), blocked by the virus check and deleted" in text
    assert text.count("SHA-256: `") == 1
    # decision and activity
    assert "- Pause until missing evidence arrives" in text and "- Note: Waiting on landlord call" in text
    assert "Noted what a file says about the monthly rent" in text


def test_never_claims_safety(client, outbox):
    case_id, _ = busy_case(client, outbox)
    text = export(client, case_id).text.lower()
    for phrase in ("is safe", "safe to pay", "verified listing", "legit", "scam"):
        assert phrase not in text


def test_share_version_leaves_out_private_details(client, outbox):
    case_id, _ = busy_case(client, outbox)
    res = export(client, case_id, include_notes="false")
    text = res.text
    assert "-to-share.md" in res.headers["content-disposition"]
    assert "leaves out the renter's private notes" in text
    for private in ("Page 1 names Jordan", "Waiting on landlord call", "Jordan (Messenger)", "facebook.com"):
        assert private not in text
    assert "monthly rent differs from the listing" in text  # the rules' reasons stay
    assert "- Pause until missing evidence arrives" in text


def test_empty_case(client, outbox):
    sign_in(client, outbox)
    res = create(client, monthly_rent="900", deposit=None, start_date=None, end_date=None,
                 payment_method=None, contact_handle=None, source_url=None)
    assert res.status_code == 201, res.text
    case_id = res.json()["id"]
    text = export(client, case_id).text
    assert "- Deposit: not stated" in text and "- Dates: not stated" in text
    assert "Nothing noted from files yet" in text
    assert "No files received." in text
    assert "- No decision recorded" in text
    assert "## Payment" not in text


def test_typed_text_cannot_inject_markdown(client, outbox):
    sign_in(client, outbox)
    case_id = create(client, address="<img src=x onerror=alert(1)> [click](http://evil.example) **bold**\n# Heading").json()["id"]
    text = export(client, case_id).text
    line = next(l for l in text.splitlines() if l.startswith("- Address:"))
    # Every special character is backslash-escaped, so viewers show it as plain text.
    assert r"\<img" in line and r"\[click\](" in line and r"\*\*bold\*\*" in line
    assert "<img" not in line.replace(r"\<img", "")
    assert "\n# Heading" not in text


def test_esc():
    assert esc("a_b *c* [d](e) <f> `g` |h|\nnext") == r"a\_b \*c\* \[d\](e) \<f\> \`g\` \|h\| next"


def test_export_is_audited(client, db, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    export(client, case_id)
    export(client, case_id, include_notes="false")
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "case.exported").order_by(AuditEvent.created_at)).all()
    assert [e.detail for e in events] == [{"notes": "included"}, {"notes": "left_out"}]
    descriptions = [a["description"] for a in client.get(f"/cases/{case_id}/activity").json()]
    assert "Downloaded a case summary" in descriptions
    assert "Downloaded a case summary to share (without private notes)" in descriptions


def test_strangers_and_signed_out_cannot_export(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    as_other_user(client, outbox)
    assert export(client, case_id).status_code == 404
    client.cookies.clear()
    assert export(client, case_id).status_code == 401


def test_website_can_read_the_file_name(client, outbox):
    sign_in(client, outbox)
    case_id = create(client).json()["id"]
    res = client.get(f"/cases/{case_id}/export", headers={"Origin": "http://localhost:3000"})
    assert "content-disposition" in res.headers["access-control-expose-headers"].lower()