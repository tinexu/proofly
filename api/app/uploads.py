"""Receiving the subletter's files (Week 6, Day 3; spec F04).

Rules:
- Only files for the items the link asked for.
- PDF, PNG, JPEG, WebP or HEIC, detected from the file's contents (its first
  bytes), not from its name or the type the browser claims.
- At most 10 MB per file, 3 files per item, 10 files in total.
- The subletter must tick the consent box.
- One reply per link: the link closes as soon as a reply is accepted.

Everything is checked before anything is stored. If storing fails half way,
the files already stored are removed and the link stays open.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import record
from app.evidence_requests import find_open_by_token
from app.models import Case, Evidence, EvidenceRequest
from app.rules import apply_rules
from app.security import hash_token
from app.storage import Storage, new_key

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_ITEM = 3
MAX_FILES_TOTAL = 10


class UploadRejected(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class LinkClosed(Exception):
    """The link is unknown, expired, revoked, already used, or its case is gone."""


@dataclass
class IncomingFile:
    claim_type: str
    filename: str
    data: bytes


@dataclass
class Accepted:
    claim_type: str
    name: str
    content_type: str
    data: bytes
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self.sha256 = hashlib.sha256(self.data).hexdigest()


def detect_type(data: bytes) -> str | None:
    """The real file type from its first bytes, or None if it isn't one we accept."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "image/heic"
    return None


def clean_name(filename: str) -> str:
    """A safe name for display only: no folders, no odd characters, not too long."""
    base = re.split(r"[\\/]", filename or "")[-1]
    base = re.sub(r"[^A-Za-z0-9 ._()\-]", "_", base).strip(" .")
    base = re.sub(r"_+", "_", base)
    return (base or "file")[:100]


def check_files(files: list[IncomingFile], allowed_items: list[str]) -> list[Accepted]:
    if not files:
        raise UploadRejected("Add at least one file.")
    if len(files) > MAX_FILES_TOTAL:
        raise UploadRejected(f"Send at most {MAX_FILES_TOTAL} files.")
    per_item: dict[str, int] = {}
    accepted: list[Accepted] = []
    for f in files:
        if f.claim_type not in allowed_items:
            raise UploadRejected("A file was sent for something this link didn't ask for.")
        per_item[f.claim_type] = per_item.get(f.claim_type, 0) + 1
        if per_item[f.claim_type] > MAX_FILES_PER_ITEM:
            raise UploadRejected(f"Send at most {MAX_FILES_PER_ITEM} files per item.")
        name = clean_name(f.filename)
        if not f.data:
            raise UploadRejected(f"{name} is empty.")
        if len(f.data) > MAX_FILE_BYTES:
            raise UploadRejected(f"{name} is larger than 10 MB.", status_code=413)
        kind = detect_type(f.data)
        if kind is None:
            raise UploadRejected(f"{name} isn't a PDF or an image (PNG, JPG, WebP, HEIC).", status_code=415)
        accepted.append(Accepted(claim_type=f.claim_type, name=name, content_type=kind, data=f.data))
    return accepted


def _claim_the_link(db: Session, token: str, now: datetime) -> EvidenceRequest | None:
    """Mark the link answered in one statement, so two replies at once can't both get in."""
    req_id = db.scalar(
        update(EvidenceRequest)
        .where(
            EvidenceRequest.token_hash == hash_token(token),
            EvidenceRequest.revoked_at.is_(None),
            EvidenceRequest.responded_at.is_(None),
            EvidenceRequest.expires_at > now,
            EvidenceRequest.case_id.in_(select(Case.id).where(Case.status == "active")),
        )
        .values(responded_at=now)
        .returning(EvidenceRequest.id)
    )
    return db.get(EvidenceRequest, req_id) if req_id else None


def receive(db: Session, storage: Storage, token: str, consent: bool, files: list[IncomingFile]) -> list[Evidence]:
    """Check, store and record a subletter's reply. Raises LinkClosed or UploadRejected."""
    req = find_open_by_token(db, token)
    if req is None:
        raise LinkClosed()
    if not consent:
        raise UploadRejected("Please confirm you choose to share these files.")
    accepted = check_files(files, list(req.scopes))

    now = datetime.now(timezone.utc)
    req = _claim_the_link(db, token, now)
    if req is None:  # closed between the check and now (expired, revoked or answered)
        db.rollback()
        raise LinkClosed()

    stored: list[str] = []
    try:
        rows: list[Evidence] = []
        for a in accepted:
            key = new_key()
            storage.put(key, a.data, a.content_type)
            stored.append(key)
            rows.append(Evidence(
                case_id=req.case_id, request_id=req.id, claim_type=a.claim_type, source="subletter",
                storage_key=key, original_name=a.name, content_type=a.content_type,
                size_bytes=len(a.data), sha256=a.sha256, uploaded_at=now,
            ))
        db.add_all(rows)

        record(db, "evidence.received", actor_type="subletter", case_id=req.case_id, file_count=len(rows))
        db.flush()
        apply_rules(db, db.get(Case, req.case_id))  # claims with files move to "evidence received"
        db.commit()
        return rows
    except Exception:
        db.rollback()
        for key in stored:
            try:
                storage.delete(key)
            except Exception:
                pass  # best effort; a leftover file has no database row, so it's never served
        raise