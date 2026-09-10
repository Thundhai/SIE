"""Milestone test items 15-17: StorageProvider behavior, path-traversal
protection, and file-size validation.
"""

import pytest

from app.ingestion.hashing import sha256_hex
from app.ingestion.storage import LocalFilesystemStorageProvider, StorageError


# --- 15. StorageProvider behavior -----------------------------------------


def test_save_then_retrieve_round_trips(tmp_path):
    provider = LocalFilesystemStorageProvider(tmp_path)
    data = b"safety procedure content"
    content_hash = sha256_hex(data)

    reference = provider.save(content_hash=content_hash, extension=".txt", data=data)

    assert provider.exists(storage_reference=reference)
    assert provider.retrieve(storage_reference=reference) == data


def test_delete_removes_the_object(tmp_path):
    provider = LocalFilesystemStorageProvider(tmp_path)
    data = b"content"
    reference = provider.save(content_hash=sha256_hex(data), extension=".txt", data=data)

    provider.delete(storage_reference=reference)

    assert not provider.exists(storage_reference=reference)


def test_exists_is_false_for_an_unsaved_reference(tmp_path):
    provider = LocalFilesystemStorageProvider(tmp_path)
    fake_hash = "0" * 64

    reference = f"{fake_hash[:2]}/{fake_hash[2:4]}/{fake_hash}.txt"
    assert not provider.exists(storage_reference=reference)


def test_storage_reference_is_a_relative_key_not_an_absolute_path(tmp_path):
    provider = LocalFilesystemStorageProvider(tmp_path)
    data = b"content"

    reference = provider.save(content_hash=sha256_hex(data), extension=".pdf", data=data)

    assert not reference.startswith("/")
    assert str(tmp_path) not in reference


def test_save_shards_files_across_subdirectories(tmp_path):
    provider = LocalFilesystemStorageProvider(tmp_path)
    data = b"content"
    content_hash = sha256_hex(data)

    reference = provider.save(content_hash=content_hash, extension=".txt", data=data)

    assert reference == f"{content_hash[:2]}/{content_hash[2:4]}/{content_hash}.txt"
    assert (tmp_path / content_hash[:2] / content_hash[2:4] / f"{content_hash}.txt").is_file()


# --- 16. Path traversal protection -----------------------------------------


@pytest.mark.parametrize(
    "malicious_reference",
    [
        "../../../etc/passwd",
        "../../etc/shadow",
        "ab/cd/../../../etc/passwd",
        "/etc/passwd",
        "ab/cd/not-a-real-hash.txt",
        "ab/cd/" + ("a" * 64) + ".exe.txt",  # not matching the strict key shape
    ],
)
def test_retrieve_rejects_unsafe_storage_references(tmp_path, malicious_reference):
    provider = LocalFilesystemStorageProvider(tmp_path)

    with pytest.raises(StorageError):
        provider.retrieve(storage_reference=malicious_reference)


def test_exists_returns_false_rather_than_raising_for_unsafe_references(tmp_path):
    """exists() is a plain boolean check used defensively elsewhere, so it
    swallows the StorageError rather than propagating it."""
    provider = LocalFilesystemStorageProvider(tmp_path)

    assert provider.exists(storage_reference="../../../etc/passwd") is False


def test_a_malicious_filename_never_reaches_the_storage_path():
    """save() never uses the caller-supplied filename for anything
    path-related at all — the key is derived purely from the content
    hash and a sanitized extension."""
    from app.ingestion.storage import _key_for

    key = _key_for(sha256_hex(b"content"), "../../etc/passwd")
    assert ".." not in key
    assert "/etc/" not in key
    # An unsafe "extension" is sanitized down to a safe fallback.
    assert key.endswith(".bin")


# --- 17. File size validation ----------------------------------------------


def test_max_upload_size_is_configured_and_positive():
    from app.core.config import settings

    assert settings.MAX_UPLOAD_SIZE_BYTES > 0
