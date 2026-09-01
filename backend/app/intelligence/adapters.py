"""DataSourceAdapter — milestone item 8. The one abstraction boundary
between SIE's canonical event model and any external system's own
representation. `SafetyEventIngestionService` (the DB-facing
orchestration layer, mirroring `EmbeddingService`/`ChunkingService`'s own
"pure transformation stage + DB-facing orchestration stage" split
elsewhere in this codebase) depends on this `Protocol` only — never on
Safelytic, or any other named vendor, directly (milestone item 4: "SIE
must not be Safelytic-only").

`GenericJSONAdapter` is the one adapter actually exercised by the REST
ingestion API (`app/api/v1/intelligence.py`) — it accepts a payload
already shaped close to the canonical schema (a generic JSON/CSV-derived
record), performs no source-specific transformation of its own, and
implements every method the `Protocol` requires. A future
Safelytic-specific (or CSV-column-mapping, or any other source's)
adapter implements the same four methods with its own `transform()`
logic (e.g. mapping that source's own field names/severity scale before
handing off to the shared `validate`/`normalize` functions) without any
call site above it changing.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.intelligence.schemas import NormalizedSafetyEvent, RawSafetyEventPayload, ValidationResult
from app.intelligence.validation import validate_and_normalize


@runtime_checkable
class DataSourceAdapter(Protocol):
    """`validate` / `normalize` / `transform` / `ingest` — exactly the
    milestone's own conceptual interface (item 8)."""

    source_system_name: str

    def validate(self, raw: RawSafetyEventPayload) -> ValidationResult:
        """Deterministic validation only — see app/intelligence/validation.py.
        Never mutates `raw`."""
        ...

    def normalize(
        self, raw: RawSafetyEventPayload, *, organization_id: uuid.UUID
    ) -> NormalizedSafetyEvent | None:
        """Returns `None` iff `validate(raw)` would report `"REJECTED"` —
        see that status's own docstring."""
        ...

    def transform(self, normalized: NormalizedSafetyEvent) -> NormalizedSafetyEvent:
        """Adapter-specific enrichment/mapping hook, applied *after* the
        shared validate/normalize step — e.g. a source-specific severity
        remap that the generic normalizer wouldn't know about. The
        generic adapter's own `transform` is a no-op."""
        ...

    def ingest(
        self, db: Session, *, organization_id: uuid.UUID, raw: RawSafetyEventPayload, batch_id: uuid.UUID
    ):
        """The one method that actually writes to the database — see
        `app/intelligence/ingestion_service.py::SafetyEventIngestionService`,
        which every adapter's `ingest()` delegates to so idempotency and
        provenance stamping happen in exactly one place."""
        ...


class GenericJSONAdapter:
    """The default adapter — see module docstring."""

    source_system_name = "generic"

    def validate(self, raw: RawSafetyEventPayload) -> ValidationResult:
        # validate_and_normalize() takes organization_id only to stamp it
        # onto the NormalizedSafetyEvent it builds -- no validation rule
        # reads it, so a throwaway id is safe here; this method only
        # returns the ValidationResult half of that pair.
        result, _ = validate_and_normalize(raw, organization_id=uuid.uuid4())
        return result

    def normalize(
        self, raw: RawSafetyEventPayload, *, organization_id: uuid.UUID
    ) -> NormalizedSafetyEvent | None:
        _, normalized = validate_and_normalize(raw, organization_id=organization_id)
        return normalized

    def transform(self, normalized: NormalizedSafetyEvent) -> NormalizedSafetyEvent:
        return normalized

    def ingest(
        self, db: Session, *, organization_id: uuid.UUID, raw: RawSafetyEventPayload, batch_id: uuid.UUID
    ):
        from app.intelligence.ingestion_service import safety_event_ingestion_service

        return safety_event_ingestion_service.ingest_event(
            db, organization_id=organization_id, payload=raw, adapter=self, batch_id=batch_id
        )
