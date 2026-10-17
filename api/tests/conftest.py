"""Shared test setup.

Database tests run against a separate `proofly_test` database (created
automatically next to your dev database), so they never touch your dev data.
If Postgres isn't running, database tests are skipped and the rest still run.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_session
from app.email import get_email_sender
from app.scanner import ScanResult, get_scanner
from app.storage import StorageError, _check_key, get_storage
from app.main import app

TEST_DB_NAME = "proofly_test"


def _test_url() -> str:
    url = make_url(get_settings().database_url).set(database=TEST_DB_NAME)
    return url.render_as_string(hide_password=False)


def _ensure_test_database() -> None:
    admin_url = make_url(get_settings().database_url).set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = url
    return cfg


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    try:
        _ensure_test_database()
    except Exception as exc:  # Postgres not running
        pytest.skip(f"Postgres not reachable, skipping database tests ({exc.__class__.__name__}). Run `docker compose up -d`.")
    url = _test_url()
    cfg = alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


class CapturingEmailSender:
    """Keeps sent emails in a list instead of printing them."""

    def __init__(self) -> None:
        self.sent: list = []

    def send(self, email) -> None:
        self.sent.append(email)


@pytest.fixture
def outbox() -> CapturingEmailSender:
    return CapturingEmailSender()


class MemoryStorage:
    """File storage kept in a dict, for tests. Can be told to fail."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.fail_after: int | None = None  # fail on the Nth put
        self.puts = 0

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        self.puts += 1
        if self.fail_after is not None and self.puts > self.fail_after:
            raise StorageError("storage is down")
        self.files[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        if key not in self.files:
            raise StorageError("File not found.")
        return self.files[key][0]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


class FakeScanner:
    """Says "clean" unless told otherwise. Files containing b"EVIL" count as infected."""

    def __init__(self) -> None:
        self.up = True
        self.fail = False  # reachable but every scan errors
        self.scanned = 0

    def ping(self) -> bool:
        return self.up

    def scan(self, data: bytes) -> ScanResult:
        self.scanned += 1
        if not self.up or self.fail:
            return ScanResult("error", "fake failure")
        if b"EVIL" in data:
            return ScanResult("infected", "Fake.Test.Virus")
        return ScanResult("clean")


@pytest.fixture
def scanner() -> FakeScanner:
    return FakeScanner()


@pytest.fixture
def client(db: Session, outbox: CapturingEmailSender, storage: MemoryStorage, scanner: FakeScanner) -> Iterator[TestClient]:
    """An API client wired to the per-test database, a fake outbox, in-memory storage and a fake scanner."""
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_email_sender] = lambda: outbox
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_scanner] = lambda: scanner
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after each test."""
    connection = db_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()