"""XML adapter — architecture and basic parsing only, same posture as
json_adapter.py:

    Raw XML -> format validation -> schema identification -> mapping
    layer -> canonical SIE data

Uses `defusedxml` rather than the standard library's `xml.etree` — this
adapter parses untrusted uploaded input, and defusedxml specifically
guards against XML attack classes (entity expansion/"billion laughs",
external entity resolution) that the stdlib parser does not reject by
default. This is the security requirement ("treat all uploaded files as
untrusted input") applied to this one format, not a general parsing
upgrade.

Each direct child of the root element becomes one NormalizedContent
(its tag as `title`, its text content, and its own attributes/children
serialized into `metadata`) — again, a small, schema-agnostic
usefulness rather than an attempt at real mapping, which is future work.
"""

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError

from app.ingestion.adapters.base import (
    AdapterExtractionError,
    AdapterValidationError,
    ExtractionResult,
)
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


def _element_to_text(element) -> str:
    return "".join(element.itertext()).strip()


class XMLAdapter:
    format_id = "xml"
    content_category = "structured_data"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "application/xml" or extension == ".xml"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            DefusedET.fromstring(file_bytes)
        except ParseError as exc:
            raise AdapterValidationError(f"File is not valid XML: {exc}") from exc
        except DefusedXmlException as exc:
            raise AdapterValidationError(f"File rejected as unsafe XML: {exc}") from exc
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        try:
            root = DefusedET.fromstring(file_bytes)
        except (ParseError, DefusedXmlException) as exc:
            # validate() should already have been called first and raised
            # for this, but extract() must not trust that and re-parse
            # unsafe/malformed input regardless.
            raise AdapterExtractionError(f"Failed to parse XML content: {exc}") from exc
        children = list(root)
        return ExtractionResult(
            raw={"root": root, "children": children},
            metadata={
                "root_tag": root.tag,
                "child_count": len(children),
                "schema_identified": False,  # see module docstring
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        children = extraction.raw["children"]
        if not children:
            # No child elements at all (e.g. <status>ok</status>) — the
            # root itself is the one record worth normalizing.
            root = extraction.raw["root"]
            text = _element_to_text(root)
            if not text:
                return []
            return [
                NormalizedContent(
                    content_type=NormalizedContentType.STRUCTURED_RECORD,
                    text=text,
                    title=root.tag,
                    metadata={"tag": root.tag, "attributes": dict(root.attrib)},
                )
            ]

        contents: list[NormalizedContent] = []
        for index, child in enumerate(children, start=1):
            attributes = dict(child.attrib)
            contents.append(
                NormalizedContent(
                    content_type=NormalizedContentType.STRUCTURED_RECORD,
                    text=_element_to_text(child),
                    title=child.tag,
                    row_number=index,
                    metadata={"tag": child.tag, "attributes": attributes},
                    source_reference=f"Element {index}: <{child.tag}>",
                )
            )
        return contents
