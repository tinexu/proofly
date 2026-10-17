"""Virus scanning with ClamAV (Week 6, Day 4).

Talks to a running clamd over TCP using its INSTREAM command: the file's bytes
are streamed to the scanner and never written to the scanner's disk. No extra
Python package is needed.

Results:
- "clean"    : nothing found
- "infected" : a signature matched (the name is returned)
- "error"    : the scanner couldn't give an answer (down, timed out, too big...)

Anything other than "clean" keeps a file locked. Errors fail closed.
"""

import socket
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

from app.config import Settings, get_settings

CHUNK = 64 * 1024

# The standard, harmless antivirus test string (https://www.eicar.org).
# Used only by `python -m app.scan --selftest` to prove the scanner works.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass(frozen=True)
class ScanResult:
    verdict: Literal["clean", "infected", "error"]
    detail: str = ""


class Scanner(Protocol):
    def ping(self) -> bool: ...
    def scan(self, data: bytes) -> ScanResult: ...


class ClamdScanner:
    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def _connect(self) -> socket.socket:
        return socket.create_connection((self.host, self.port), timeout=self.timeout)

    @staticmethod
    def _read_reply(sock: socket.socket) -> str:
        chunks = []
        while True:
            part = sock.recv(4096)
            if not part:
                break
            chunks.append(part)
            if part.endswith(b"\0"):
                break
        return b"".join(chunks).rstrip(b"\0").decode("utf-8", "replace").strip()

    def ping(self) -> bool:
        try:
            with self._connect() as sock:
                sock.sendall(b"zPING\0")
                return self._read_reply(sock) == "PONG"
        except OSError:
            return False

    def scan(self, data: bytes) -> ScanResult:
        try:
            with self._connect() as sock:
                sock.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), CHUNK):
                    chunk = data[i:i + CHUNK]
                    sock.sendall(struct.pack("!L", len(chunk)) + chunk)
                sock.sendall(struct.pack("!L", 0))
                reply = self._read_reply(sock)
        except OSError as e:
            return ScanResult("error", f"scanner unreachable: {e.__class__.__name__}")
        # Replies look like "stream: OK", "stream: Some-Signature FOUND", or "... ERROR".
        if reply.endswith("OK") and "FOUND" not in reply:
            return ScanResult("clean")
        if reply.endswith("FOUND"):
            return ScanResult("infected", reply.removeprefix("stream:").removesuffix("FOUND").strip())
        return ScanResult("error", reply[:200] or "empty reply")


def build_scanner(settings: Settings) -> Scanner:
    return ClamdScanner(settings.clamd_host, settings.clamd_port, settings.clamd_timeout_seconds)


@lru_cache
def _scanner() -> Scanner:
    return build_scanner(get_settings())


def get_scanner() -> Scanner:
    """FastAPI dependency (tests replace it with a fake)."""
    return _scanner()