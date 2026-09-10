"""Format adapters: one class per input format, implementing the common
`DocumentAdapter` interface (base.py), plus the registry that picks one
by detected media type/extension.

Only the adapters this milestone requires are registered — see
ADAPTER_REGISTRY at the bottom of registry.py and the README's format
matrix for exactly which formats have a working adapter today versus
which are recognized by detection but not yet implemented.
"""

from app.ingestion.adapters.base import (
    AdapterValidationError,
    DocumentAdapter,
    ExtractionResult,
)
from app.ingestion.adapters.registry import get_adapter, register_adapter

__all__ = [
    "DocumentAdapter",
    "ExtractionResult",
    "AdapterValidationError",
    "get_adapter",
    "register_adapter",
]
