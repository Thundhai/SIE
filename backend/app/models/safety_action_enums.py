"""Enumerations for the Actions / Intervention domain — SIE Milestone 17:
Actions & Intervention Foundation v0.1.

Mirrors `app/predictions/enums.py`'s own stated philosophy (a domain
that needs a real, enforced state machine gets its own small enums
module, distinct from `app/models/enums.py`, which is scoped to the
knowledge/identity domains). Unlike `SafetyEvent.event_type`/`status`
(deliberately open, free-text vocabularies — see that model's own
docstring), the milestone spec is explicit that `ActionStatus`,
`ActionPriority`, and `ActionType` are *governed* vocabularies with real
transition rules to enforce — so these are backed by native PostgreSQL
enum columns (`app/models/safety_action.py`), not plain strings. This is
safe from migration 0005's enum-type-creation defect (see
`app/models/safety_event.py`'s docstring and the README's "Known gaps"
section): that defect was specifically about `add_column` on an
*already-existing* table not auto-creating the enum type it references;
`safety_actions` is a brand-new table created via `op.create_table()`,
which does create the type, exactly like every other native-enum column
already in this schema (`knowledge_sources.scope_type`,
`organization_memberships.status`, ...).
"""

from enum import Enum


class ActionStatus(str, Enum):
    """The action lifecycle. `COMPLETED`/`CANCELLED` are terminal — see
    `is_allowed_action_transition()` below. Nothing in this codebase
    transitions a status automatically; every transition is a deliberate,
    separately-authorized `POST /actions/{id}/status` call
    (`app/api/v1/actions.py`)."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ActionPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    """Deliberately compact — milestone §6's own instruction: "keep this
    vocabulary intentionally compact... do not build a complete ontology
    framework for actions in this milestone." Contrast
    `app/models/ontology_concept.py`'s real governance workflow for the
    (much larger, still-evolving) safety-event terminology; actions do
    not get that treatment here."""

    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"
    INVESTIGATION = "INVESTIGATION"
    FOLLOW_UP = "FOLLOW_UP"
    CONTROL_IMPROVEMENT = "CONTROL_IMPROVEMENT"
    OTHER = "OTHER"


# The milestone spec's own transition table (§4), verbatim. Anything not
# listed here is refused -- in particular, nothing transitions *out of*
# COMPLETED or CANCELLED (both map to an empty frozenset): closure is
# permanent in this milestone, and a terminal action is never silently
# reopened. See app/api/v1/actions.py's own docstring for why this is a
# deliberate scope boundary, not an oversight.
_ALLOWED_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.OPEN: frozenset(
        {ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.IN_PROGRESS: frozenset(
        {ActionStatus.BLOCKED, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.BLOCKED: frozenset(
        {ActionStatus.IN_PROGRESS, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.COMPLETED: frozenset(),
    ActionStatus.CANCELLED: frozenset(),
}

ACTION_TERMINAL_STATUSES: frozenset[ActionStatus] = frozenset({ActionStatus.COMPLETED, ActionStatus.CANCELLED})


def is_allowed_action_transition(current: str, target: str) -> bool:
    """Mirrors `app.predictions.enums.is_allowed_transition()` exactly:
    an unrecognized `current`/`target` string is simply not an allowed
    transition (returns `False`), never an exception -- the caller (the
    status endpoint) already validated `target` is a real `ActionStatus`
    via the request schema; `current` always comes from a persisted row,
    which can only ever hold a real enum value."""
    try:
        return ActionStatus(target) in _ALLOWED_TRANSITIONS[ActionStatus(current)]
    except ValueError:
        return False
