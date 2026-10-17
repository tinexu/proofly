"""Week 6, Day 4: the real ClamAV scanner. Skipped unless clamd is reachable.

Locally: `docker compose up -d` starts it (give it a few minutes the first time).
"""

import pytest

from app.config import get_settings
from app.scanner import EICAR, ClamdScanner

settings = get_settings()
scanner = ClamdScanner(settings.clamd_host, settings.clamd_port, timeout=10)

pytestmark = pytest.mark.skipif(not scanner.ping(), reason="ClamAV (clamd) isn't running")


def test_clean_file():
    assert scanner.scan(b"%PDF-1.7 a perfectly ordinary file").verdict == "clean"


def test_eicar_test_file_is_found():
    result = scanner.scan(EICAR)
    assert result.verdict == "infected"
    assert "eicar" in result.detail.lower()


def test_large_file_streams_in_chunks():
    assert scanner.scan(b"%PDF-1.7 " + b"0" * (3 * 1024 * 1024)).verdict == "clean"


def test_unreachable_scanner_is_an_error_not_clean():
    down = ClamdScanner("127.0.0.1", 1, timeout=1)
    assert down.ping() is False
    assert down.scan(b"anything").verdict == "error"