"""PPTX adapter — one NormalizedContent per slide, carrying its title,
body text, speaker notes, and any table content together, so a future
training-content retrieval feature can cite "Slide 17" the way the
milestone spec's own example shows.

Image *references* (shape names/counts) are recorded in metadata; the
image content itself is not extracted or OCR'd here — see
app/ingestion/ocr.py and the README's OCR architecture section.
"""

import io

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


class PPTXAdapter:
    format_id = "pptx"
    content_category = "presentation"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type.endswith("presentationml.presentation") or extension == ".pptx"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            Presentation(io.BytesIO(file_bytes))
        except Exception as exc:
            raise AdapterValidationError(f"Not a valid PPTX presentation: {exc}") from exc
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        warnings: list[str] = []
        prs = Presentation(io.BytesIO(file_bytes))

        slides = []
        for index, slide in enumerate(prs.slides, start=1):
            title = slide.shapes.title.text.strip() if slide.shapes.title else None

            text_parts: list[str] = []
            tables: list[list[list[str]]] = []
            image_count = 0
            for shape in slide.shapes:
                if shape.has_table:
                    table = shape.table
                    tables.append(
                        [[cell.text for cell in row.cells] for row in table.rows]
                    )
                    continue
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image_count += 1
                    continue
                if shape.has_text_frame and shape != slide.shapes.title:
                    text = shape.text_frame.text.strip()
                    if text:
                        text_parts.append(text)

            notes = None
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                notes = notes_text or None

            if not title and not text_parts and not tables:
                warnings.append(f"Slide {index} has no extractable title, text, or tables.")

            slides.append(
                {
                    "slide_number": index,
                    "title": title,
                    "text_parts": text_parts,
                    "notes": notes,
                    "tables": tables,
                    "image_count": image_count,
                }
            )

        return ExtractionResult(
            raw={"slides": slides},
            warnings=warnings,
            metadata={"slide_count": len(slides)},
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        contents: list[NormalizedContent] = []
        for slide in extraction.raw["slides"]:
            body_text = "\n".join(slide["text_parts"])
            metadata = {
                "image_count": slide["image_count"],
                "tables": slide["tables"],
            }
            if slide["notes"]:
                metadata["speaker_notes"] = slide["notes"]

            contents.append(
                NormalizedContent(
                    content_type=NormalizedContentType.TEXT,
                    text=body_text,
                    title=slide["title"],
                    slide_number=slide["slide_number"],
                    metadata=metadata,
                    source_reference=f"Slide {slide['slide_number']}",
                )
            )
        return contents
