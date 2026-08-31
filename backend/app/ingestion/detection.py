"""File type / media type detection.

Deliberately does not depend on `python-magic`/`libmagic` — that's a
system-level shared library this codebase's Docker image and every
deployment target would otherwise need to install, for a capability a
short, explicit signature table already covers for the formats this
milestone supports. Detection here combines:

  1. A small table of magic-byte signatures for the binary formats that
     have one (PDF, the ZIP-based Office formats, common image formats).
  2. A file-extension fallback/cross-check for text-based formats that
     have no reliable magic bytes (CSV, TXT, RTF, JSON, XML) and for
     resolving DOCX/XLSX/PPTX, which all share the same outer ZIP
     signature and are only distinguished by extension at this layer
     (each adapter's own `validate()` double-checks by actually trying
     to open the archive with its format library — see
     adapters/docx_adapter.py etc.).

`detect_file_type()` never raises for unrecognized content: it returns
`None`, and it is the caller's job (the ingestion pipeline / adapter
registry) to decide that an undetected type is unsupported. This module
only detects; it does not decide what's allowed.
"""

from dataclasses import dataclass

# (signature bytes, offset) -> media type. Checked in order; first match
# wins. ZIP-based Office formats all share the same outer signature and
# are disambiguated by extension in `detect_file_type`.
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),  # DOCX/XLSX/PPTX/generic zip
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),  # TIFF, little-endian
    (b"MM\x00*", "image/tiff"),  # TIFF, big-endian
    (b"{\\rtf1", "application/rtf"),
]

_EXTENSION_MEDIA_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    # Recognized-but-future formats (see README format matrix): detection
    # still identifies them (so the ingestion response can say "DOC is
    # not supported yet" rather than "unknown file"), they just have no
    # registered adapter.
    ".doc": "application/msword",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".xls": "application/vnd.ms-excel",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
}

_ZIP_EXTENSION_MEDIA_TYPES: dict[str, str] = {
    ".docx": _EXTENSION_MEDIA_TYPES[".docx"],
    ".xlsx": _EXTENSION_MEDIA_TYPES[".xlsx"],
    ".pptx": _EXTENSION_MEDIA_TYPES[".pptx"],
}


@dataclass(frozen=True)
class DetectedFileType:
    media_type: str
    extension: str


def file_extension(filename: str) -> str:
    """Extract a lowercased extension (with leading dot) from a filename,
    stripping any directory components first — the filename is untrusted
    input and must never be used as-is for anything path-like. Returns
    "" if there is none."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return "." + base.rsplit(".", 1)[-1].lower()


def detect_file_type(file_bytes: bytes, *, filename: str) -> DetectedFileType | None:
    """Detect the media type of `file_bytes`, cross-checked against
    `filename`'s extension. Returns None if nothing matches."""
    extension = file_extension(filename)

    sniffed: str | None = None
    for signature, media_type in _MAGIC_SIGNATURES:
        if file_bytes.startswith(signature):
            sniffed = media_type
            break

    if sniffed == "application/zip":
        # Disambiguate the Office Open XML formats by extension; a ZIP
        # signature alone is ambiguous.
        zip_media_type = _ZIP_EXTENSION_MEDIA_TYPES.get(extension)
        if zip_media_type is not None:
            return DetectedFileType(media_type=zip_media_type, extension=extension)
        return None  # a real ZIP, or an Office format we don't recognize by extension

    if sniffed is not None:
        return DetectedFileType(media_type=sniffed, extension=extension)

    # No magic-byte match (typical for text-based formats) — fall back to
    # the extension table.
    extension_media_type = _EXTENSION_MEDIA_TYPES.get(extension)
    if extension_media_type is not None:
        return DetectedFileType(media_type=extension_media_type, extension=extension)

    return None
