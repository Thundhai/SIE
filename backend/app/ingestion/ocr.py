"""OCR provider abstraction — interface only, no implementation.

Per the milestone spec, no commercial OCR is implemented in this
release. This module exists so the future pipeline shape is already
decided and adapters can be written against it without a rewrite later:

    Input -> OCR detection -> OCR provider -> Extracted text -> Normalized content

`OCRProvider` is the plug-in boundary a future implementation (a local
model, or a commercial API) would satisfy. `is_ocr_available()` reports
whether one is currently configured; nothing in this codebase currently
registers one, so it always returns False today, and any code path that
would need OCR (a scanned PDF, a JPG/PNG/TIFF image) instead records
`extraction_method = NONE` (or, for a PDF whose text layer came up
empty, still `TEXT_EXTRACTION`, since that method genuinely was
attempted — see app/ingestion/adapters/pdf_adapter.py) with an explicit
warning, rather than silently pretending text was extracted.
"""

from typing import Protocol


class OCRProvider(Protocol):
    def extract_text(self, image_bytes: bytes, *, media_type: str) -> str:
        """Return the text OCR'd from `image_bytes`. A real implementation
        should raise rather than return an empty string on failure, so
        the pipeline can distinguish "OCR found no text" from "OCR
        failed" — this milestone has no implementation to enforce that
        against, so it's stated here for whoever writes the first one.
        """
        ...


_provider: OCRProvider | None = None


def get_ocr_provider() -> OCRProvider | None:
    """Returns the configured OCRProvider, or None if none is registered
    (always None in this milestone). Callers must handle None rather
    than assume OCR is always available."""
    return _provider


def is_ocr_available() -> bool:
    return get_ocr_provider() is not None
