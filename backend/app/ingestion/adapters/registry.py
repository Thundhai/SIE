"""Adapter registry: picks a `DocumentAdapter` for a detected media
type/extension.

Deliberately not a big if/elif ladder in the ingestion service — adding a
format means writing one adapter module and adding it to
`_DEFAULT_ADAPTERS` below, nothing else in the pipeline changes.
"""

from app.ingestion.adapters.base import DocumentAdapter

_adapters: list[DocumentAdapter] = []


def register_adapter(adapter: DocumentAdapter) -> None:
    _adapters.append(adapter)


def get_adapter(*, media_type: str, extension: str) -> DocumentAdapter | None:
    for adapter in _adapters:
        if adapter.detect(media_type=media_type, extension=extension):
            return adapter
    return None


def registered_format_ids() -> list[str]:
    return [adapter.format_id for adapter in _adapters]


def _load_default_adapters() -> None:
    from app.ingestion.adapters.csv_adapter import CSVAdapter
    from app.ingestion.adapters.docx_adapter import DOCXAdapter
    from app.ingestion.adapters.image_adapter import ImageAdapter
    from app.ingestion.adapters.json_adapter import JSONAdapter
    from app.ingestion.adapters.pdf_adapter import PDFAdapter
    from app.ingestion.adapters.pptx_adapter import PPTXAdapter
    from app.ingestion.adapters.rtf_adapter import RTFAdapter
    from app.ingestion.adapters.txt_adapter import TXTAdapter
    from app.ingestion.adapters.xlsx_adapter import XLSXAdapter
    from app.ingestion.adapters.xml_adapter import XMLAdapter

    for adapter_cls in (
        PDFAdapter,
        DOCXAdapter,
        TXTAdapter,
        RTFAdapter,
        CSVAdapter,
        XLSXAdapter,
        PPTXAdapter,
        JSONAdapter,
        XMLAdapter,
        ImageAdapter,
    ):
        register_adapter(adapter_cls())


_load_default_adapters()
