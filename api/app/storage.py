"""Private file storage for evidence (Week 6, Day 3).

Two backends with the same three operations (put, get, delete):
- "local": a private folder (api/.storage by default). For development only.
- "s3":    an S3 bucket (Amazon S3 or anything S3-compatible). For production.

Keys are random and chosen by the API, never by the uploader, so a file name
can't be used to reach other files. Nothing here makes a file public.
"""

import os
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings

KEY_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class StorageError(RuntimeError):
    pass


def new_key() -> str:
    return secrets.token_hex(16)


def _check_key(key: str) -> None:
    if not KEY_PATTERN.fullmatch(key):
        raise StorageError("Invalid storage key.")


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Files in one private folder. Fine for one developer's laptop, not for production."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _check_key(key)
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        tmp = path.with_suffix(".part")
        # Owner-only permissions; write to a temp file then rename, so a crash never leaves half a file.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as e:
            raise StorageError("File not found.") from e

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """A private S3 bucket. Objects are encrypted at rest by S3 (SSE-S3)."""

    def __init__(self, bucket: str, region: str, endpoint_url: str | None = None) -> None:
        import boto3  # imported here so local development doesn't need AWS set up

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url or None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
        )

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey as e:
            raise StorageError("File not found.") from e

    def delete(self, key: str) -> None:
        _check_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        if settings.is_production:
            raise RuntimeError("Local file storage can't be used in production. Set PROOFLY_STORAGE_BACKEND=s3.")
        return LocalStorage(settings.storage_dir)
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.s3_region, settings.s3_endpoint_url)
    raise RuntimeError(f"Unknown storage backend: {settings.storage_backend!r}")


@lru_cache
def _storage() -> Storage:
    return build_storage(get_settings())


def get_storage() -> Storage:
    """FastAPI dependency (tests replace it with an in-memory store)."""
    return _storage()