"""Analytics -- deterministic, rule-based point-in-time summary, trend
series, and risk signals computed from recorded safety events. See
../../docs/BOUNDARY_DECISIONS.md Section 8 for the Analytics boundary.

Mirrors the *observable shape* of Thundhai/SIE's existing
AnalyticsSummaryRead/RiskSignalRead, deliberately re-derived rather
than copied -- see attention.py's own docstring for the identical
reasoning. The internal FeatureValue/IndicatorValue/RiskSignal
dataclasses (app/intelligence/features.py, indicators.py, signals.py --
private) carry `calculation_version` strings and raw internal
SafetyEvent ids that are implementation detail, not observable output,
and are redacted here exactly the way AttentionItemDTO redacts
AttentionEvidence: `calculation_version` is dropped, and a signal's raw
`supporting_event_ids` are retyped as `EvidenceType.SAFETY_EVENT`
`EvidenceReference`s (this codebase's own established "event_ids =
SafetyEvent ids" convention).

`source_reliability` (app/intelligence/reliability.py) has deliberately
no analog anywhere in this module: it describes per-source-system
ingestion-pipeline bookkeeping internal to Commercial Core, not an
intelligence *output* an external consumer reasons about -- the same
"do not expose internal bookkeeping merely because it exists"
governance `attention.py`'s own module docstring already applies to
`AttentionEvidence.calculation_version`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.common import AsOfWindow, EvidenceReference


class AnalyticsDataSufficiency(str, Enum):
    """Mirrors the small, stable vocabulary Thundhai/SIE's own
    `data_sufficiency` field already uses -- whether a result rests on
    enough recorded events to be meaningful."""

    SUFFICIENT_DATA = "SUFFICIENT_DATA"
    LIMITED_DATA = "LIMITED_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnalyticsIndicatorCategory(str, Enum):
    """Leading vs. lagging -- never a predictive probability, both are
    indicators."""

    LEADING = "LEADING"
    LAGGING = "LAGGING"


class AnalyticsSignalSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnalyticsTrendDirection(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnalyticsIndicatorDTO(BaseModel):
    """One leading/lagging indicator value. See module docstring for
    exactly which internal fields were deliberately left out."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description=(
            "Open vocabulary, e.g. 'incident_count', 'training_completion_rate'. "
            "Current known values documented in BOUNDARY_DECISIONS.md, informational only."
        ),
    )
    category: AnalyticsIndicatorCategory
    value: float | None = Field(default=None, description="None when the underlying feature could not be computed -- see unavailable_reason.")
    unavailable_reason: str | None = None


class AnalyticsSignalDTO(BaseModel):
    """One deterministic, rule-based risk signal. Never a prediction,
    never a probability -- see module docstring."""

    model_config = ConfigDict(frozen=True)

    signal_type: str = Field(
        ...,
        description=(
            "Open vocabulary, e.g. 'OVERDUE_ACTION_SURGE'. Current known values "
            "documented in BOUNDARY_DECISIONS.md, informational only."
        ),
    )
    severity: AnalyticsSignalSeverity
    observed_period_start: datetime = Field(..., description="UTC.")
    observed_period_end: datetime = Field(..., description="UTC.")
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when this signal is site-scoped; None when organization-scoped.")
    evidence: list[EvidenceReference] = Field(default_factory=list)


class AnalyticsTrendPeriodDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_start: datetime
    period_end: datetime
    value: float | None


class AnalyticsTrendDTO(BaseModel):
    """A trend series for one named metric, period-bucketed and
    classified. See `AnalyticsTrendDirection` for the closed
    classification vocabulary."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when this trend is site-scoped; None when organization-scoped.")
    metric: str = Field(
        ...,
        description=(
            "Open vocabulary naming the trend metric, e.g. 'incident_count'. "
            "Current known values documented in BOUNDARY_DECISIONS.md, informational only."
        ),
    )
    as_of: AsOfWindow
    direction: AnalyticsTrendDirection
    periods: list[AnalyticsTrendPeriodDTO] = Field(default_factory=list)
    slope: float | None = None
    relative_slope: float | None = None


class AnalyticsSummaryDTO(BaseModel):
    """A point-in-time analytics summary: event count, data sufficiency,
    leading/lagging indicators, and the risk signals currently firing."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when this summary is site-scoped; None when organization-scoped.")
    as_of: AsOfWindow
    event_count: int = Field(..., ge=0)
    data_sufficiency: AnalyticsDataSufficiency
    indicators: list[AnalyticsIndicatorDTO] = Field(default_factory=list)
    signals: list[AnalyticsSignalDTO] = Field(default_factory=list)


class AnalyticsSignalsResultDTO(BaseModel):
    """The risk signals currently firing for one organization/scope/as_of
    -- the standalone-signals read's own envelope, mirroring
    `AttentionResultDTO`'s identical organization/scope/as_of-echo
    shape rather than returning a bare, context-free list."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when this read is site-scoped; None when organization-scoped.")
    as_of: AsOfWindow
    signals: list[AnalyticsSignalDTO] = Field(default_factory=list)
