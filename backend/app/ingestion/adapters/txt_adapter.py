"""Plain text adapter — the simplest adapter, and a good reference for
the interface: one file in, one NormalizedContent out."""

from app.ingestion.adapters.base import ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


class TXTAdapter:
    format_id = "txt"
    content_category = "document"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "text/plain" or extension == ".txt"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        return []  # decoding failures are handled (with a warning) in extract()

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        warnings: list[str] = []
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="replace")
            warnings.append(
                "File was not valid UTF-8; decoded with invalid byte sequences replaced."
            )
        return ExtractionResult(raw=text, warnings=warnings)

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        text: str = extraction.raw
        return [
            NormalizedContent(
                content_type=NormalizedContentType.TEXT,
                text=text,
            )
        ]
