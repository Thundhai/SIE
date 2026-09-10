"""Project lifecycle vocabulary — SIE Milestone 35: Organizational &
Operational Scope Foundation v0.1.

A small, closed, native-enum vocabulary — mirrors `SafetyActionStatus`'s
own precedent (`app/models/safety_action_enums.py`): a project's
lifecycle is a genuinely closed set a database CHECK is the right amount
of structure for, unlike `SafetyEvent.event_type` (open-ended, expected
to grow via data alone — see that model's own docstring for the
contrast). `Project` carries identity and lifecycle only — no task
list, no schedule, no budget; see `app/models/project.py`'s own
docstring for the full "what this entity deliberately is not" rationale.
"""

from enum import Enum


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


__all__ = ["ProjectStatus"]
