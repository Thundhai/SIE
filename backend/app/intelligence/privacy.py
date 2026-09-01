"""Privacy controls for organizational safety data — milestone item 34.

Safety data can carry sensitive employee information (a name in an
incident description, a personal id in a structured field, medical or
disciplinary detail) that has no place in aggregate analytics or in a
log line. This module is the one place that decision is made, so every
caller (ingestion audit logging, feature/signal computation, the
analytics API) applies the same rule rather than each reinventing it.

**What is sensitive:**

  * `SafetyEvent.description` — free text, entirely unclassified, always
    treated as sensitive. Never included in any feature/signal/analytics
    output; never logged unless `settings.LOG_INTELLIGENCE_EVENT_DESCRIPTION`
    is explicitly enabled (default `False`).
  * Any `SafetyEvent.attributes` key listed in
    `settings.INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS` (e.g.
    `employee_name`, `employee_id`, `medical_details`,
    `disciplinary_action`) — redacted wherever `attributes` would
    otherwise be surfaced.

This is a classification/exclusion mechanism, not encryption or field-
level access control — those remain future work if a deployment needs
them; see the README's "Privacy" section for what this milestone does
and does not implement.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings


def is_sensitive_attribute_key(key: str) -> bool:
    return key in settings.INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS


def redact_sensitive_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Returns a copy of `attributes` with every sensitive key's value
    replaced by a `"[REDACTED]"` marker — the key itself (and every
    non-sensitive value) is preserved, so a caller can still see *that*
    e.g. an `employee_id` was recorded without seeing its value."""
    if not attributes:
        return {}
    return {
        key: ("[REDACTED]" if is_sensitive_attribute_key(key) else value)
        for key, value in attributes.items()
    }


def safe_description_for_logging(description: str | None) -> str | None:
    """Never the raw description, unless a deployment has explicitly
    opted in — the same `LOG_*_TEXT` pattern already used by
    `RetrievalService`/`RAGService` (see `app/core/config.py`)."""
    if description is None:
        return None
    return description if settings.LOG_INTELLIGENCE_EVENT_DESCRIPTION else "[REDACTED]"
