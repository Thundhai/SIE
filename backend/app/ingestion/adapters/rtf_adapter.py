"""RTF adapter, using `striprtf` — a small, pure-Python, dependency-free
RTF-to-text converter (no shell-out, no native library), matching the
milestone's "an available safe parser" guidance. RTF markup/formatting is
discarded; only the text content survives, normalized the same as a
plain-text document."""

from striprtf.striprtf import rtf_to_text

from app.ingestion.adapters.base import (
    AdapterExtractionError,
    AdapterValidationError,
    ExtractionResult,
)
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


class RTFAdapter:
    format_id = "rtf"
    content_category = "document"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "application/rtf" or extension == ".rtf"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        if not file_bytes.startswith(b"{\\rtf"):
            raise AdapterValidationError("File does not start with an RTF header ('{\\rtf').")
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        warnings: list[str] = []
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
            warnings.append("File was not valid UTF-8; decoded as Latin-1 before RTF parsing.")

        try:
            text = rtf_to_text(raw_text)
        except Exception as exc:  # striprtf has no narrower exception type
            raise AdapterExtractionError(f"Failed to parse RTF content: {exc}") from exc

        return ExtractionResult(raw=text, warnings=warnings)

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        return [NormalizedContent(content_type=NormalizedContentType.TEXT, text=extraction.raw)]
