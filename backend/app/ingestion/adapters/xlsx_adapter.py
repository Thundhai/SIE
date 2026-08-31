"""XLSX adapter — one NormalizedContent per row per worksheet, never one
blob for the whole workbook, so a future citation can say "Sheet:
Incident Register, Row 124" (see the module docstring in
normalized_content.py for the general principle this follows).

The first non-empty row of each sheet is treated as its header; every
following non-empty row becomes one structured record keyed by that
header. Like the CSV adapter, this makes no attempt to classify *what*
the data represents — that's the future canonical-mapping layer's job.
"""

import io

from openpyxl import load_workbook

from app.ingestion.adapters.base import AdapterValidationError, ExtractionResult
from app.ingestion.normalized_content import NormalizedContent, NormalizedContentType


class XLSXAdapter:
    format_id = "xlsx"
    content_category = "spreadsheet"

    def detect(self, *, media_type: str, extension: str) -> bool:
        return media_type.endswith("spreadsheetml.sheet") or extension == ".xlsx"

    def validate(self, file_bytes: bytes, *, filename: str) -> list[str]:
        try:
            load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as exc:
            raise AdapterValidationError(f"Not a valid XLSX workbook: {exc}") from exc
        return []

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        warnings: list[str] = []
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)

        sheets = []
        for ws in wb.worksheets:
            all_rows = [
                [("" if cell is None else cell) for cell in row]
                for row in ws.iter_rows(values_only=True)
            ]
            non_empty = [row for row in all_rows if any(str(c).strip() for c in row)]
            if not non_empty:
                warnings.append(f"Sheet {ws.title!r} contains no non-empty rows; skipped.")
                sheets.append({"name": ws.title, "header": [], "rows": []})
                continue

            header = [str(c) if c != "" else f"column_{i + 1}" for i, c in enumerate(non_empty[0])]
            data_rows = non_empty[1:]
            sheets.append({"name": ws.title, "header": header, "rows": data_rows})

        wb.close()

        return ExtractionResult(
            raw={"sheets": sheets},
            warnings=warnings,
            metadata={
                "sheet_names": [s["name"] for s in sheets],
                "sheet_count": len(sheets),
            },
        )

    def normalize(self, extraction: ExtractionResult) -> list[NormalizedContent]:
        contents: list[NormalizedContent] = []
        for sheet in extraction.raw["sheets"]:
            header: list[str] = sheet["header"]
            for offset, row in enumerate(sheet["rows"]):
                row_number = offset + 2  # header occupies row 1
                values = {h: v for h, v in zip(header, row, strict=False)}
                contents.append(
                    NormalizedContent(
                        content_type=NormalizedContentType.STRUCTURED_RECORD,
                        text=", ".join(f"{k}: {v}" for k, v in values.items()),
                        sheet_name=sheet["name"],
                        row_number=row_number,
                        metadata={"columns": header, "values": values},
                        source_reference=f"Sheet: {sheet['name']}, Row {row_number}",
                    )
                )
        return contents
