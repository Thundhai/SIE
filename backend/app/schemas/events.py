"""Human-facing Events read API schemas — SIE Enterprise Read API &
Browser Integration Foundation v0.1.

Read-only response shapes for `GET /api/v1/events` and
`GET /api/v1/events/{event_id}` (see `app/api/v1/events.py`), built
directly from the existing, unmodified `SafetyEvent` model
(`app/models/safety_event.py`) — no second, competing event model
invented for the frontend. Distinct from
`app.schemas.intelligence.SafetyEventCreate`, which is the machine-client
*ingestion* write schema; this module is read-only and human-facing.

**Evidence/knowledge references are deliberately absent from
`SafetyEventDetailRead`.** `SafetyEvent` has no relationship to a
knowledge document, an evidence record, or another event (its own
`correlation_id` is explicitly documented, on the model itself, as
"never interpreted or validated by SIE itself, purely a pass-through
provenance field" — resolving it into a fabricated "related record" list
would violate that). Rather than inventing one to make the existing
Event Detail UX look complete, this schema simply does not carry those
fields; the frontend's own `ApiEventRepository` maps that absence onto
its existing `finding: null` / `evidence: []` / `relevantKnowledge: []`
shape — which its `InsightPanel` component was already built to render
as an honest "insufficient evidence" state (see
`src/features/events/apiEventRepository.ts` and
`src/components/intelligence/InsightPanel.tsx`), not a redesign.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SafetyEventSummaryRead(BaseModel):
    """One row of `GET /events` — narrower than `SafetyEventDetailRead`:
    no `description` (privacy-sensitive free text, not needed in a list
    view), no `attributes`/`source_value` (large, domain-specific JSON),
    no provenance detail beyond `source_system` (enough for the list's
    own "Source" column)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_time: datetime
    event_type: str
    event_subtype: str | None
    site_id: uuid.UUID | None
    site_name: str | None
    status: str | None
    severity: str | None
    source_system: str
    source_record_id: str
    data_quality_status: str
    # SIE Milestone 35A: the governed project attribution -- NULL means
    # unattributed (the default, and every pre-M35A row's permanent
    # state unless explicitly attributed). Distinct from the free-text
    # `project` field on SafetyEventDetailRead below -- see
    # app/models/safety_event.py's own docstring.
    attributed_project_id: uuid.UUID | None = None


class EventProvenanceRead(BaseModel):
    """Where this record came from and how it got here — milestone §6.
    Every field mirrors a real `SafetyEvent`/`DataSource` column; nothing
    here is computed or invented."""

    organization_id: uuid.UUID
    source_system: str
    source_record_id: str
    source_record_version: str | None
    source_schema_version: str | None
    ingestion_batch_id: uuid.UUID
    ingestion_source_id: uuid.UUID | None
    data_source_name: str | None
    ingestion_time: datetime
    normalization_version: str
    schema_version: str
    correlation_id: str | None


class SafetyEventDetailRead(BaseModel):
    """`GET /events/{event_id}`'s own response — enough for the existing
    Event Detail screen's core-information and provenance sections (§6).
    See this module's own docstring for why evidence/knowledge/related-
    record fields are absent rather than fabricated (§7)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    site_name: str | None
    event_type: str
    event_subtype: str | None
    event_time: datetime
    period_end: datetime | None
    reported_time: datetime | None
    status: str | None
    severity: str | None
    potential_severity: str | None
    description: str | None
    location: str | None
    project: str | None
    department: str | None
    contractor: str | None
    activity: str | None
    attributes: dict
    data_quality_status: str
    data_quality_issues: list | None
    provenance: EventProvenanceRead
    # SIE Milestone 35A -- see SafetyEventSummaryRead's own field
    # docstring above; `attributed_project_name` is resolved by the
    # route (one extra by-id lookup, same pattern as `site_name`/
    # `provenance.data_source_name` above), never fabricated when NULL.
    attributed_project_id: uuid.UUID | None = None
    attributed_project_name: str | None = None


class EventListRead(BaseModel):
    """`GET /events`'s own response — deliberately not the generic
    `ResponseEnvelope` (which carries no pagination metadata): `total`
    lets the caller render "Showing X–Y of total" and compute page count
    without a second request, `page`/`page_size` echo back exactly what
    was requested (never nondeterministic re-derivation)."""

    items: list[SafetyEventSummaryRead]
    total: int
    page: int
    page_size: int
