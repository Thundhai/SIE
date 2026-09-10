"""Enumerations for the intelligence/predictive-analytics domain.

Mirrors `app/models/enums.py`'s own stated philosophy: only vocabularies
that drive real, closed business logic become enums here; everything the
milestone spec itself describes as open-ended (`event_subtype`, `status`,
`location`, `department`, `contractor`, `activity`) stays a free-form
string on `SafetyEvent` — see that model's own docstring. These enums are
Python-side validation/type-safety only; the corresponding database
columns are plain, indexed `String` columns, not native PostgreSQL enum
types (see `app/models/safety_event.py`'s docstring for why, including
the migration-0005 precedent this deliberately avoids repeating).
"""

from enum import Enum


class SafetyEventType(str, Enum):
    """The eleven data domains the milestone spec names (item 5).
    Recognized, but not closed at the database level — an unrecognized
    value is a data-quality *degradation* (see
    `app/intelligence/validation.py`), never an outright rejection, so a
    twelfth domain can be added without a migration."""

    INCIDENT = "INCIDENT"
    NEAR_MISS = "NEAR_MISS"
    OBSERVATION = "OBSERVATION"
    INSPECTION = "INSPECTION"
    AUDIT = "AUDIT"
    CORRECTIVE_ACTION = "CORRECTIVE_ACTION"
    PERMIT = "PERMIT"
    TRAINING = "TRAINING"
    WORKFORCE = "WORKFORCE"
    EQUIPMENT = "EQUIPMENT"
    ENVIRONMENTAL = "ENVIRONMENTAL"


class SeverityLevel(str, Enum):
    """The normalized severity vocabulary `app/intelligence/normalization.py`
    maps a source system's own severity scale onto — see that module for
    the alias table. `source_value` always preserves whatever the source
    system actually sent (milestone item 14)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DataQualityStatus(str, Enum):
    """A record's data-quality state — deliberately distinct from *risk*
    and from *prediction confidence* (milestone item 13): a record can be
    `DataQualityStatus.LOW`-ish (`PARTIAL`) while describing a `HIGH`
    severity event; the two concepts never collapse into one field or
    one score anywhere in this codebase.

    `QUARANTINED` records are stored (never silently dropped — milestone
    item 12) but excluded from every feature/indicator/signal
    calculation, exactly like `INVALID` ones — see
    `app/intelligence/temporal.py`."""

    VALID = "VALID"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"


class IngestionOutcome(str, Enum):
    """What actually happened to one record during ingestion — distinct
    from `DataQualityStatus` (a property of the stored row, if one was
    stored at all). `REJECTED_INVALID` is the one outcome with no
    corresponding database row (see
    `app/intelligence/ingestion_service.py`)."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SKIPPED_IDEMPOTENT = "SKIPPED_IDEMPOTENT"
    REJECTED_INVALID = "REJECTED_INVALID"
    # Enterprise Data Ingestion & Validation Foundation v0.1, item 8's
    # source-record-versioning cases -- both only ever produced when the
    # incoming record and the existing stored row both carry an
    # integer-parseable source_record_version (see
    # app/intelligence/ingestion_service.py::_version_ordering()); a
    # non-versioned or non-numeric-versioned resend can never produce
    # either of these, and continues to behave exactly as before this
    # milestone (UPDATED/SKIPPED_IDEMPOTENT only).
    SKIPPED_STALE_VERSION = "SKIPPED_STALE_VERSION"
    REJECTED_VERSION_CONFLICT = "REJECTED_VERSION_CONFLICT"


class DataSufficiency(str, Enum):
    """Whether an analytical result rests on enough data to be
    meaningful (milestone item 30) — see `app/intelligence/sufficiency.py`
    for the exact, configurable thresholds. A site with three days of
    data must never be compared to one with three years of data without
    this label attached."""

    SUFFICIENT_DATA = "SUFFICIENT_DATA"
    LIMITED_DATA = "LIMITED_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TrendDirection(str, Enum):
    """See `app/intelligence/trends.py` for the exact statistical method
    (documented, not hidden — milestone item 23)."""

    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnomalyStatus(str, Enum):
    """See `app/intelligence/anomaly.py` for the exact z-score method
    (milestone item 24) — an explainable, documented statistical method,
    never a black box."""

    NORMAL = "NORMAL"
    ANOMALOUS = "ANOMALOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnomalyDirection(str, Enum):
    """Whether the current value sits above, below, or exactly at its
    baseline mean — SIE Milestone 23: Enterprise Intelligence
    Explainability & Anomaly Foundation v0.1, item 5. Deliberately
    separate from `AnomalyStatus`: "unusually high" and "unusually low"
    are both `ANOMALOUS`, but operationally very different, and this
    codebase never collapses the two into one undifferentiated signal
    (milestone item 5's own instruction — "do not automatically call
    every increase 'bad'"). `NONE` covers both `INSUFFICIENT_DATA` (no
    baseline to compare against) and the exact-equality case (current
    value equals the baseline mean precisely — no direction at all, not
    an arbitrary tie-break)."""

    ABOVE_BASELINE = "ABOVE_BASELINE"
    BELOW_BASELINE = "BELOW_BASELINE"
    NONE = "NONE"


class RiskSignalType(str, Enum):
    """The deterministic signal types the milestone's own example list
    names (item 22). Every one of these is a rule-based detection over
    features — never called a prediction (milestone item 22's own
    instruction) and never a probability (item 29)."""

    OVERDUE_ACTION_SURGE = "OVERDUE_ACTION_SURGE"
    HIGH_POTENTIAL_EVENT_CLUSTER = "HIGH_POTENTIAL_EVENT_CLUSTER"
    TRAINING_COMPLIANCE_DROP = "TRAINING_COMPLIANCE_DROP"
    EQUIPMENT_FAILURE_CLUSTER = "EQUIPMENT_FAILURE_CLUSTER"
    UNSAFE_OBSERVATION_SURGE = "UNSAFE_OBSERVATION_SURGE"


class RiskSignalSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IndicatorCategory(str, Enum):
    """Leading vs. lagging — milestone item 21. Never called a
    "predictive probability"; both are indicators, not predictions."""

    LEADING = "LEADING"
    LAGGING = "LAGGING"


# --- SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation v0.1 ---


class EnterpriseTrendClassification(str, Enum):
    """The semantic (good/bad), not merely directional, trend label
    milestone item 6 asks for — deliberately distinct from
    `TrendDirection` above (`INCREASING`/`DECREASING`), which says
    nothing about whether an increase is good or bad news for a given
    metric. `app/intelligence/enterprise_trend.py`'s period-over-period
    comparison of the primary lagging metric (total INCIDENT count) is
    the one place this codebase decides "more incidents" is always
    DETERIORATING and "fewer incidents" is always IMPROVING — see that
    module's own docstring for the exact, documented, deterministic
    rule."""

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RecurrenceClassification(str, Enum):
    """See `app/intelligence/recurrence.py` for the exact,
    `settings.ENTERPRISE_RECURRENCE_*`-driven thresholds (milestone item
    8). `NONE` exists for completeness/testability
    (`classify_recurrence()` is total over every non-negative count) but
    is never emitted by the pattern-detection sweep itself — a
    single-occurrence "pattern" isn't a pattern at all, so it is simply
    never returned."""

    NONE = "NONE"
    WATCH = "WATCH"
    RECURRING = "RECURRING"
    HIGH_RECURRENCE = "HIGH_RECURRENCE"


class ConcentrationClassification(str, Enum):
    """A ranked contributor's share of its dimension's total, banded —
    see `app/intelligence/concentration.py` (milestone item 7). Named
    distinctly from `RiskClassification` below so a 35%
    "site concentration" reading is never confused with, or accidentally
    compared numerically against, the overall 0-100 enterprise risk
    score — the two are unrelated scales measuring unrelated things."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


# --- SIE Milestone 24: Enterprise Intelligence Pattern & Correlation Foundation v0.1 ---


class AssociationClassification(str, Enum):
    """Strength/direction band for a Pearson correlation between two
    aligned metric period-series — SIE Milestone 24: Enterprise
    Intelligence Pattern & Correlation Foundation v0.1, item 5. A finer
    vocabulary than `app/intelligence/association.py`'s own pre-existing,
    unchanged `outcome` field (`ASSOCIATION_OBSERVED`/
    `NO_ASSOCIATION_OBSERVED`/`INSUFFICIENT_DATA`) — that field is kept
    exactly as-is for backward compatibility with its pre-existing
    callers/tests; `classification` is the new, richer band this
    milestone's own `EnterpriseAssociationResult` exposes. Deliberately
    has no `CAUSATION_*` member and never will — see
    `app/intelligence/association.py`'s own hard causal boundary, which
    this vocabulary is designed to make structurally impossible to
    violate: there is no member here that could be read as a causal
    claim, only strength and direction of co-movement."""

    STRONG_POSITIVE = "STRONG_POSITIVE"
    MODERATE_POSITIVE = "MODERATE_POSITIVE"
    WEAK = "WEAK"
    MODERATE_NEGATIVE = "MODERATE_NEGATIVE"
    STRONG_NEGATIVE = "STRONG_NEGATIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RiskClassification(str, Enum):
    """The deterministic enterprise risk score's band — see
    `app/intelligence/risk_score.py` (milestone items 9-10). A
    prioritization label, never a probability and never a claim of
    causation — see that module's own docstring."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
