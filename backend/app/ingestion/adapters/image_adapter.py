"""Image adapter (JPG/PNG/TIFF) — architecture support only.

    Image -> OCR -> extracted text -> image metadata -> page/document relationship

Per the milestone spec, no OCR is implemented yet (see
app/ingestion/ocr.py) and none is required for this adapter to exist: it
still validates the file is a real, openable image and records genuine
image metadata (dimensions, format, mode) via Pillow, but produces no
text content — `metadata["ocr_required"]` is always True here, which the
ingestion service reads to record `extraction_method = NONE` (or `OCR`,
once a provider exists — see app/ingestion/ocr.py) rather than
`TEXT_EXTRACTION`, since no text was actually extracted. This is the
concrete expression of the milestone's "do not silently pretend
extraction succeeded" principle for a format this release cannot read
the content of at all.
"""

import io

from PIL import Image, UnidentifiedImageError

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType
from app.ingestion.ocr import is_ocr_available


class ImageAdapter:
    format_id = "image"
    content_category = "image"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type in {"image/jpeg", "image/png", "image/tiff"} or extension in {
            ".jpg",
            ".jpeg",
            ".png",
            ".tif",
            ".tiff",
        }

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            with Image.open(io.BytesIO(file_bytes)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise AdapterValidationError(f"Not a valid image: {exc}") from exc
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        with Image.open(io.BytesIO(file_bytes)) as image:
            width, height = image.size
            image_format = image.format
            mode = image.mode

        warnings = [
            "No OCR provider is configured; image content was not extracted as text "
            "(see app/ingestion/ocr.py)."
        ]
        return ExtractionResult(
            raw={"width": width, "height": height, "format": image_format, "mode": mode},
            warnings=warnings,
            metadata={
                "width": width,
                "height": height,
                "format": image_format,
                "ocr_required": True,
                "ocr_available": is_ocr_available(),
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        return [
            NormalizedContent(
                content_type=NormalizedContentType.IMAGE,
                text="",
                metadata={
                    "width": extraction.raw["width"],
                    "height": extraction.raw["height"],
                    "format": extraction.raw["format"],
                    "ocr_required": True,
                },
            )
        ]
