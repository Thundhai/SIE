"""PDF adapter — one NormalizedContent per page, always carrying its
page number, since that's what a future evidence citation needs
("Chunk -> page_number = 47", per the milestone spec).

Text extraction only (`pypdf`'s built-in text layer reader) — this
adapter does not run OCR and does not promise table extraction. Both are
explicit, recorded facts rather than silent gaps:

  * If pages contain no extractable text (typical of a scanned PDF with
    no text layer), that is recorded as a warning naming exactly how many
    pages, not silently produced as empty content — see the ingestion
    engine's fail-safely principle. `extraction_method` for this adapter
    is always TEXT_EXTRACTION; recognizing a scanned PDF and running OCR
    on it is future work (app/ingestion/ocr.py).
  * Table extraction is not attempted — `pypdf` has no reliable table
    structure reader, and a fragile heuristic would be worse than
    admitting the gap. `extraction.metadata["table_extraction"]` is
    always `"not_attempted"` so this is visible to callers, not implied
    by silence.

Section detection is a light, best-effort heuristic (a short, non-blank
first line on a page is treated as that page's section title) — clearly
not a real layout/heading analysis, and only ever used to populate
`section_title`, never to change what text is extracted.
"""

import io

from pypdf import PdfReader

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType

_MAX_HEURISTIC_HEADING_LENGTH = 80


class PDFAdapter:
    format_id = "pdf"
    content_category = "document"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "application/pdf" or extension == ".pdf"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception as exc:
            raise AdapterValidationError(f"Not a valid PDF: {exc}") from exc

        if reader.is_encrypted:
            try:
                reader.decrypt("")  # some PDFs are "encrypted" with an empty owner password
            except Exception:
                pass
            if reader.is_encrypted:
                raise AdapterValidationError("PDF is password-protected; cannot extract content.")
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            reader.decrypt("")

        doc_info = reader.metadata or {}
        pages = []
        empty_page_count = 0
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                empty_page_count += 1
            pages.append({"page_number": index, "text": text})

        warnings: list[str] = []
        if empty_page_count:
            warnings.append(
                f"PDF text extraction completed with {empty_page_count} of {len(pages)} "
                "page(s) containing no extractable text."
            )

        return ExtractionResult(
            raw={"pages": pages},
            warnings=warnings,
            metadata={
                "page_count": len(pages),
                "pages_with_no_text": empty_page_count,
                "table_extraction": "not_attempted",
                "document_title": doc_info.get("/Title") if doc_info else None,
                "document_author": doc_info.get("/Author") if doc_info else None,
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        contents: list[NormalizedContent] = []
        for page in extraction.raw["pages"]:
            text: str = page["text"]
            section_title = self._guess_section_title(text)
            contents.append(
                NormalizedContent(
                    content_type=NormalizedContentType.TEXT,
                    text=text,
                    page_number=page["page_number"],
                    section_title=section_title,
                    source_reference=f"Page {page['page_number']}",
                )
            )
        return contents

    @staticmethod
    def _guess_section_title(page_text: str) -> str | None:
        """Best-effort only — see module docstring."""
        for line in page_text.splitlines():
            stripped = line.strip()
            if stripped:
                if len(stripped) <= _MAX_HEURISTIC_HEADING_LENGTH:
                    return stripped
                return None
        return None
