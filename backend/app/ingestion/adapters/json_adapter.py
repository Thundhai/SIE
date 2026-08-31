"""JSON adapter — architecture and basic parsing only, per the milestone
spec: this deliberately does not implement schema identification or a
canonical-data mapping layer.

    Raw JSON -> format validation -> schema identification -> mapping
    layer -> canonical SIE data

Only the first step is implemented here (plus one small, format-agnostic
usefulness: a top-level JSON array of objects is split one
NormalizedContent per element, since that shape is common for exported
data and splitting it costs nothing in terms of assuming a schema). A
top-level object, or an array of non-objects, is normalized as a single
record. Schema identification and the mapping layer
(observations/incidents/training/inspections/etc., per the spec) are
future work building on top of this adapter, not part of it.
"""

import json

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


class JSONAdapter:
    format_id = "json"
    content_category = "structured_data"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "application/json" or extension == ".json"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            json.loads(file_bytes.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise AdapterValidationError(f"File is not valid UTF-8: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AdapterValidationError(f"File is not valid JSON: {exc}") from exc
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        parsed = json.loads(file_bytes.decode("utf-8"))
        is_record_list = isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed)
        return ExtractionResult(
            raw=parsed,
            metadata={
                "top_level_type": type(parsed).__name__,
                "schema_identified": False,  # see module docstring
                "record_count": len(parsed) if is_record_list else 1,
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        parsed = extraction.raw
        if isinstance(parsed, list) and parsed and all(isinstance(x, dict) for x in parsed):
            return [
                NormalizedContent(
                    content_type=NormalizedContentType.STRUCTURED_RECORD,
                    text=json.dumps(item, ensure_ascii=False),
                    row_number=index + 1,
                    metadata=item,
                    source_reference=f"Record {index + 1}",
                )
                for index, item in enumerate(parsed)
            ]
        return [
            NormalizedContent(
                content_type=NormalizedContentType.STRUCTURED_RECORD,
                text=json.dumps(parsed, ensure_ascii=False, indent=2),
                metadata={"raw_type": type(parsed).__name__},
            )
        ]
