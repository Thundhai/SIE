"""Actions / Intervention API schemas — SIE Milestone 17: Actions &
Intervention Foundation v0.1. Read-only and write shapes for
`app/api/v1/actions.py`, built directly from the real, unmodified
`SafetyAction`/`SafetyActionHistory` models (`app/models/safety_action*.py`)
— no second, competing representation. `extra="forbid"` on every write
schema is deliberate: the milestone spec names an exact, closed set of
fields a client may set on create/update/status-transition; anything
else (`organization_id`, `status` via PATCH, `completed_at`, ...) must
be rejected outright, not silently ignored (see each schema's own
docstring for exactly which fields that protects).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.safety_action_enums import ActionPriority, ActionStatus, ActionType

_TITLE_MAX_LENGTH = 255
_DESCRIPTION_MAX_LENGTH = 5000
_EXTERNAL_REFERENCE_MAX_LENGTH = 255
_COMMENT_MAX_LENGTH = 2000
_SEARCH_MAX_LENGTH = 200
# Bounded, like every other free-form JSON field this codebase accepts
# from a caller (§16's "do not allow arbitrary uncontrolled payload
# expansion") -- generous enough for genuine structured detail, small
# enough that `attributes` can never become a way to smuggle an
# unbounded blob past the global request-size limit
# (app/core/request_limits.py) one field at a time.
_ATTRIBUTES_MAX_BYTES = 8192


def _validate_attributes_size(value: dict) -> dict:
    size = len(json.dumps(value).encode("utf-8"))
    if size > _ATTRIBUTES_MAX_BYTES:
        raise ValueError(f"attributes must serialize to at most {_ATTRIBUTES_MAX_BYTES} bytes (got {size}).")
    return value


class SafetyActionCreate(BaseModel):
    """`POST /actions` body. `organization_id` is deliberately not a
    field here: it comes from authenticated request context
    (`organization_id` query parameter, resolved through
    `require_context_permission`), never trusted from the body — see
    `app/api/v1/actions.py`'s own docstring."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    action_type: ActionType
    priority: ActionPriority = ActionPriority.MEDIUM
    owner_user_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    due_date: datetime | None = None
    source_event_id: uuid.UUID | None = None
    external_reference: str | None = Field(default=None, max_length=_EXTERNAL_REFERENCE_MAX_LENGTH)
    attributes: dict = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def _bound_attributes(cls, value: dict) -> dict:
        return _validate_attributes_size(value)


class SafetyActionUpdate(BaseModel):
    """`PATCH /actions/{action_id}` body. Only these fields are ever
    mutable through this endpoint — `organization_id`, creator ids,
    `created_at`/`completed_at`/`cancelled_at`, and `status` are not
    part of this schema at all (status transitions go through the
    dedicated `POST /actions/{action_id}/status` endpoint instead — see
    `app/api/v1/actions.py`'s own docstring for why that separation is
    deliberate). `extra="forbid"` means an attempt to set any of those
    is a `422`, not a silently-ignored no-op.

    A field genuinely omitted from the request body is left unchanged;
    see `app/services/safety_action_service.py::apply_update()` for how
    `model_fields_set` (not the field's value) decides that — the one
    exception is `title`, which is required non-null on the model
    itself, so an explicit `null` for it is rejected rather than
    accepted and then failing at the database layer.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)
    action_type: ActionType | None = None
    priority: ActionPriority | None = None
    owner_user_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    due_date: datetime | None = None
    external_reference: str | None = Field(default=None, max_length=_EXTERNAL_REFERENCE_MAX_LENGTH)
    attributes: dict | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank.")
        return value

    @field_validator("attributes")
    @classmethod
    def _bound_attributes(cls, value: dict | None) -> dict | None:
        if value is None:
            return value
        return _validate_attributes_size(value)


class SafetyActionStatusUpdate(BaseModel):
    """`POST /actions/{action_id}/status` body — milestone §11's
    "target status, optional comment/reason", nothing else. The server
    (`app/models/safety_action_enums.py::is_allowed_action_transition`)
    is the sole authority on whether the transition is legal; this
    schema only validates that `status` is a real `ActionStatus` value."""

    model_config = ConfigDict(extra="forbid")

    status: ActionStatus
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX_LENGTH)


class SafetyActionRead(BaseModel):
    """One action, in full — used for `POST`/`GET .../{id}`/`PATCH`/
    `POST .../status` responses, and as the item shape of
    `ActionListRead.items` (the action domain has no privacy-sensitive
    field the list view needs to hide, unlike `SafetyEventSummaryRead`
    — see that schema's own docstring — so one shape covers both)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    site_name: str | None
    source_event_id: uuid.UUID | None
    title: str
    description: str | None
    action_type: ActionType
    priority: ActionPriority
    status: ActionStatus
    owner_user_id: uuid.UUID | None
    owner_name: str | None
    due_date: datetime | None
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    external_reference: str | None
    attributes: dict


class ActionListRead(BaseModel):
    """`GET /actions`'s own response — mirrors `EventListRead`'s own
    reasoning (`app/schemas/events.py`) for why this is a dedicated
    shape rather than the generic `ResponseEnvelope`: `total` lets a
    caller render "Showing X-Y of total" without a second request, and
    `page`/`page_size` echo back exactly what was requested."""

    items: list[SafetyActionRead]
    total: int
    page: int
    page_size: int
