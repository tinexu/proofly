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


@pytest.fixture
def client(db: Session, outbox: CapturingEmailSender) -> Iterator[TestClient]:
    """An API client wired to the per-test database session and a fake outbox."""
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_email_sender] = lambda: outbox
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