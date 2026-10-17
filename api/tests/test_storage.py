"""Week 6, Day 3: the two storage backends behave the same and stay private."""

import os
import stat

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.storage import LocalStorage, S3Storage, StorageError, build_storage, new_key

DATA = b"%PDF-1.7 test"


def roundtrip(store) -> None:
    key = new_key()
    store.put(key, DATA, "application/pdf")
    assert store.get(key) == DATA
    store.delete(key)
    with pytest.raises(StorageError):
        store.get(key)
    store.delete(key)  # deleting twice is fine


@pytest.mark.parametrize("bad", ["../secret", "a/b", "", "UPPERCASE00000000000000000000000", "x" * 32])
def test_keys_must_be_ours(tmp_path, bad):
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).put(bad, DATA, "application/pdf")


def test_new_keys_are_random_and_valid():
    keys = {new_key() for _ in range(100)}
    assert len(keys) == 100 and all(len(k) == 32 for k in keys)


# --- Local folder (development) -----------------------------------------------------

def test_local_roundtrip(tmp_path):
    roundtrip(LocalStorage(tmp_path / "store"))


def test_local_files_are_owner_only(tmp_path):
    store = LocalStorage(tmp_path / "store")
    key = new_key()
    store.put(key, DATA, "application/pdf")
    mode = stat.S_IMODE(os.stat(tmp_path / "store" / key).st_mode)
    assert mode == 0o600
    assert stat.S_IMODE(os.stat(tmp_path / "store").st_mode) == 0o700


def test_local_storage_refused_in_production():
    with pytest.raises(RuntimeError, match="production"):
        build_storage(Settings(env="production", storage_backend="local"))


# --- S3 (production), against an S3 emulator ------------------------------------------

@mock_aws
def test_s3_roundtrip_and_encryption():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="proofly-test")
    store = S3Storage("proofly-test", "us-east-1")
    key = new_key()
    store.put(key, DATA, "application/pdf")
    head = s3.head_object(Bucket="proofly-test", Key=key)
    assert head["ServerSideEncryption"] == "AES256"
    assert head["ContentType"] == "application/pdf"
    store.delete(key)
    roundtrip(store)


@mock_aws
def test_s3_objects_are_not_public():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="proofly-test")
    store = S3Storage("proofly-test", "us-east-1")
    key = new_key()
    store.put(key, DATA, "application/pdf")
    grants = s3.get_object_acl(Bucket="proofly-test", Key=key)["Grants"]
    assert not any(g["Grantee"].get("URI", "").endswith("AllUsers") for g in grants)