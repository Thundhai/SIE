"""CSV adapter — structured data, not prose: one NormalizedContent per
row (not one blob for the whole file), so a future citation can point at
"row 124" the same way a spreadsheet's can.

Deliberately does not guess what *kind* of safety record a CSV
represents (an incident register vs. a training log vs. an inspection
checklist) — that classification is a future canonical-mapping layer's
job (see the milestone spec's own note on this), not this adapter's. This
adapter only turns rows/columns into structured records; it stays
data-agnostic.
"""

import csv
import io

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType

_MAX_SNIFF_BYTES = 8192


class CSVAdapter:
    format_id = "csv"
    content_category = "spreadsheet"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type == "text/csv" or extension == ".csv"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        if not file_bytes.strip():
            raise AdapterValidationError("File is empty.")
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        warnings: list[str] = []

        try:
            text = file_bytes.decode("utf-8-sig")  # tolerates a BOM, common from Excel exports
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="replace")
            warnings.append(
                "File was not valid UTF-8; decoded with invalid byte sequences replaced."
            )

        sample = text[:_MAX_SNIFF_BYTES]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","
            warnings.append("Could not confidently detect a delimiter; defaulted to comma.")

        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = True
            warnings.append("Could not confidently detect a header row; assumed row 1 is one.")

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        all_rows = list(reader)
        if not all_rows:
            raise AdapterValidationError("File contains no parseable rows.")

        header = all_rows[0] if has_header else [f"column_{i + 1}" for i in range(len(all_rows[0]))]
        data_rows = all_rows[1:] if has_header else all_rows

        ragged = [i for i, row in enumerate(data_rows, start=2) if len(row) != len(header)]
        if ragged:
            warnings.append(
                f"{len(ragged)} row(s) had a different column count than the header "
                f"(first at row {ragged[0]})."
            )

        return ExtractionResult(
            raw={
                "header": header,
                "rows": data_rows,
                "has_header": has_header,
                "start_row_number": 2 if has_header else 1,
            },
            warnings=warnings,
            metadata={
                "delimiter": delimiter,
                "column_names": header,
                "row_count": len(data_rows),
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        header: list[str] = extraction.raw["header"]
        rows: list[list[str]] = extraction.raw["rows"]
        start_row_number: int = extraction.raw["start_row_number"]

        contents: list[NormalizedContent] = []
        for offset, row in enumerate(rows):
            row_number = start_row_number + offset
            values = dict(zip(header, row, strict=False))
            contents.append(
                NormalizedContent(
                    content_type=NormalizedContentType.STRUCTURED_RECORD,
                    text=", ".join(f"{k}: {v}" for k, v in values.items()),
                    row_number=row_number,
                    metadata={"columns": header, "values": values},
                    source_reference=f"Row {row_number}",
                )
            )
        return contents
