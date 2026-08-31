"""Storage abstraction for uploaded file bytes.

No ingested file's binary content is ever stored in PostgreSQL — only a
`storage_reference` string naming where it lives (see
app/models/ingested_file.py). `StorageProvider` is the interface that
reference is opaque *to*: application code never touches a filesystem
path (or, later, an S3/Azure/GCS client) directly, only this interface,
so a production deployment can swap `LocalFilesystemStorageProvider` for
an object-storage-backed implementation without changing any ingestion
logic — see `get_storage_provider()` at the bottom of this module for the
one place that decision is made.

`LocalFilesystemStorageProvider` is the only implementation in this
milestone, explicitly for local development (per spec: "For local
development, a filesystem storage abstraction is acceptable" — a
production S3/Azure/GCS implementation is future work, not built here).

Path-traversal safety does not depend on validating the caller's input:
`save()` never uses the caller-supplied filename for anything
path-related — the storage key is derived entirely from the content hash
and a validated extension, sharded into a two-level directory
(`<hash[:2]>/<hash[2:4]>/<hash><extension>`) so no single directory
accumulates every file. `retrieve()`/`delete()`/`exists()` additionally
reject any `storage_reference` that isn't exactly of that shape, as
defense in depth against a `storage_reference` value that didn't
originate from this provider's own `save()`.
"""

import re
from pathlib import Path
from typing import Protocol

_SAFE_KEY_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.[a-z0-9]{1,20}$")


class StorageError(Exception):
    """Raised for any storage operation failure, including a rejected
    (unsafe or unrecognized) storage_reference."""


class StorageProvider(Protocol):
    def save(self, *, content_hash: str, extension: str, data: bytes) -> str:
        """Persist `data` and return its storage_reference."""
        ...

    def retrieve(self, *, storage_reference: str) -> bytes: ...

    def delete(self, *, storage_reference: str) -> None: ...

    def exists(self, *, storage_reference: str) -> bool: ...


def _safe_extension(extension: str) -> str:
    ext = extension.lower().lstrip(".")
    if not ext or not re.fullmatch(r"[a-z0-9]{1,20}", ext):
        ext = "bin"
    return ext


def _key_for(content_hash: str, extension: str) -> str:
    h = content_hash.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        raise StorageError(f"content_hash must be a 64-character hex sha256 digest, got {h!r}")
    return f"{h[:2]}/{h[2:4]}/{h}.{_safe_extension(extension)}"


class LocalFilesystemStorageProvider:
    """Development-only StorageProvider backed by a directory on local
    disk. `root` is created if it doesn't exist. `storage_reference`
    values returned by `save()` are relative keys, never absolute paths —
    the API layer only ever sees and returns these opaque keys (see
    app/schemas/ingestion.py), never a filesystem path."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, *, content_hash: str, extension: str, data: bytes) -> str:
        key = _key_for(content_hash, extension)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def retrieve(self, *, storage_reference: str) -> bytes:
        path = self._resolve(storage_reference)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"no stored object for reference {storage_reference!r}") from exc

    def delete(self, *, storage_reference: str) -> None:
        path = self._resolve(storage_reference)
        path.unlink(missing_ok=True)

    def exists(self, *, storage_reference: str) -> bool:
        try:
            path = self._resolve(storage_reference)
        except StorageError:
            return False
        return path.is_file()

    def _resolve(self, storage_reference: str) -> Path:
        if not _SAFE_KEY_RE.fullmatch(storage_reference):
            raise StorageError(f"refusing unrecognized storage_reference {storage_reference!r}")
        return self.root / storage_reference


_provider: StorageProvider | None = None


def get_storage_provider() -> StorageProvider:
    """The one place ingestion code obtains a StorageProvider. Swapping
    to an object-storage-backed implementation in production means
    changing this function, not any ingestion call site."""
    global _provider
    if _provider is None:
        from app.core.config import settings

        _provider = LocalFilesystemStorageProvider(settings.INGESTION_STORAGE_DIR)
    return _provider
