"""Enterprise Intelligence -- deterministic, point-in-time enterprise
risk picture computed from recorded safety events and actions: a
deterministic risk score, trend, indicators, recurring patterns, risk
concentration, anomalies, cross-metric associations, and
human-readable explanations. See ../../docs/BOUNDARY_DECISIONS.md for
the Enterprise Intelligence boundary (Task 01D-F3).

Mirrors the *observable shape* of Thundhai/SIE's existing
EnterpriseIntelligenceRead, deliberately re-derived rather than copied
-- see attention.py's own docstring for the identical reasoning. The
internal dataclasses this module's own adapter converts
(app/intelligence/enterprise_intelligence_service.py and its sibling
enterprise_indicators.py/enterprise_trend.py/recurrence.py/
concentration.py/enterprise_anomaly.py/enterprise_association.py/
risk_score.py/explanations.py -- all private) each carry a
`calculation_version` string that is implementation detail, not
observable output, and is redacted here exactly the way
AttentionItemDTO/AnalyticsSignalDTO already redact it elsewhere in this
contract. Every internal `supporting_event_ids`/`evidence_sample_event_ids`
list of raw SafetyEvent ids is retyped as a list of
`EvidenceType.SAFETY_EVENT` `EvidenceReference`s -- this codebase's own
established "event_ids = SafetyEvent ids" convention, unchanged.

**`predictive_context` has no analog anywhere in this module.** The
internal `EnterpriseIntelligenceResult.predictive_context` field
surfaces an already-recorded ML `Prediction` row -- that is the
Predictions capability, explicitly out of scope for Task 01D-F3 (see
that task's own "Scope Exclusions"), and the existing Public SIE
frontend's own `EnterpriseIntelligence` TypeScript type already never
included it either. Nothing here fabricates or forwards it.

**`RiskScoreDTO.components`/`ExplanationItemDTO` carry no
`calculation_version` of their own** (the internal
`RiskScoreComponent`/`ExplanationItem` dataclasses never had one to
begin with) -- only `RiskScoreResult.version` (the overall scoring
methodology's own version label) is redacted here, for the same
"no model/methodology identifiers" reason `calculation_version` is
redacted everywhere else in this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.common import AsOfWindow, EvidenceReference


class EnterpriseDataSufficiency(str, Enum):
    """Mirrors Thundhai/SIE's own `data_sufficiency.status` vocabulary
    -- whether this result rests on enough recorded events to be
    meaningful."""

    SUFFICIENT_DATA = "SUFFICIENT_DATA"
    LIMITED_DATA = "LIMITED_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EnterpriseIndicatorCategory(str, Enum):
    """Leading vs. lagging -- never a predictive probability, both are
    indicators."""

    LEADING = "LEADING"
    LAGGING = "LAGGING"


class EnterpriseTrendClassification(str, Enum):
    """The semantic (good/bad), not merely directional, trend label --
    distinct from a plain increasing/decreasing direction."""

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RecurrenceClassification(str, Enum):
    NONE = "NONE"
    WATCH = "WATCH"
    RECURRING = "RECURRING"
    HIGH_RECURRENCE = "HIGH_RECURRENCE"


class ConcentrationClassification(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class EnterpriseAnomalyStatus(str, Enum):
    NORMAL = "NORMAL"
    ANOMALOUS = "ANOMALOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EnterpriseAnomalyDirection(str, Enum):
    ABOVE_BASELINE = "ABOVE_BASELINE"
    BELOW_BASELINE = "BELOW_BASELINE"
    NONE = "NONE"


class EnterpriseAssociationClassification(str, Enum):
    """Strength/direction band for a correlation between two metrics.
    Deliberately has no CAUSATION_* member and never will -- strength
    and direction of co-movement only, never a causal claim."""

    STRONG_POSITIVE = "STRONG_POSITIVE"
    MODERATE_POSITIVE = "MODERATE_POSITIVE"
    WEAK = "WEAK"
    MODERATE_NEGATIVE = "MODERATE_NEGATIVE"
    STRONG_NEGATIVE = "STRONG_NEGATIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EnterpriseRiskClassification(str, Enum):
    """The deterministic enterprise risk score's band -- a
    prioritization label, never a probability and never a claim of
    causation."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EnterpriseIndicatorDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    value: int
    category: EnterpriseIndicatorCategory
    period_start: datetime
    period_end: datetime
    window_days: int
    previous_value: int = 0
    absolute_change: int = 0
    percentage_change: float | None = None
    trend_direction: str | None = None
    unavailable_reason: str | None = None


class EnterpriseTrendDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    classification: EnterpriseTrendClassification
    metric: str
    current_value: int
    previous_value: int
    absolute_change: int
    percentage_change: float | None
    current_period_start: datetime
    current_period_end: datetime
    previous_period_start: datetime
    previous_period_end: datetime


class RecurrencePatternDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern_key: str
    scope: str
    site_id: uuid.UUID
    site_label: str
    event_type: str
    event_subtype: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    window_start: datetime
    window_end: datetime
    window_days: int
    classification: RecurrenceClassification = RecurrenceClassification.NONE
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ConcentrationContributorDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    key: str
    label: str
    count: int
    total: int
    percentage: float
    classification: ConcentrationClassification


class EnterpriseAnomalyDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    label: str
    status: EnterpriseAnomalyStatus
    direction: EnterpriseAnomalyDirection
    current_value: float
    baseline_mean: float | None
    baseline_stdev: float | None
    z_score: float | None
    baseline_period_count: int
    current_period_start: datetime
    current_period_end: datetime
    window_days: int
    supporting_event_count: int
    baseline_window_start: datetime | None = None
    baseline_window_end: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class EnterpriseAssociationDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_a: str
    metric_b: str
    label_a: str
    label_b: str
    classification: EnterpriseAssociationClassification
    correlation_coefficient: float | None
    period_count: int
    period_start: datetime | None
    period_end: datetime | None
    window_days: int
    values_a: list[float] = Field(default_factory=list)
    values_b: list[float] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class RiskScoreComponentDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    raw_score: float
    weight: float
    normalized_weight: float
    contribution: float


class RiskScoreDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float | None
    classification: EnterpriseRiskClassification | None
    components: list[RiskScoreComponentDTO] = Field(default_factory=list)
    insufficient_data_reason: str | None = None


class ExplanationItemDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    value: float | int | None = None
    baseline: float | int | None = None
    contribution: float | None = None
    evidence_reference: str = ""


class ActionsContextDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_action_count: int
    overdue_action_count: int
    high_priority_action_count: int


class EnterpriseIntelligenceProvenanceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    window_start: datetime
    window_end: datetime
    event_count: int
    total_supporting_events: int
    evidence_sample: list[EvidenceReference] = Field(default_factory=list)


class EnterpriseIntelligenceResultDTO(BaseModel):
    """The top-level Enterprise Intelligence read -- organization- or
    site-scoped. See module docstring for what is deliberately absent
    (`predictive_context`, every `calculation_version`)."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    scope: str = Field(..., description="'organization' or 'site'.")
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when scope == 'site'; None when scope == 'organization'.")
    as_of: AsOfWindow
    data_sufficiency: EnterpriseDataSufficiency
    event_count: int = Field(..., ge=0)
    deterministic_risk: RiskScoreDTO
    trend: EnterpriseTrendDTO
    indicators: list[EnterpriseIndicatorDTO] = Field(default_factory=list)
    patterns: list[RecurrencePatternDTO] = Field(default_factory=list)
    concentrations: list[ConcentrationContributorDTO] = Field(default_factory=list)
    anomalies: list[EnterpriseAnomalyDTO] = Field(default_factory=list)
    associations: list[EnterpriseAssociationDTO] = Field(default_factory=list)
    explanations: list[ExplanationItemDTO] = Field(default_factory=list)
    provenance: EnterpriseIntelligenceProvenanceDTO
    actions_context: ActionsContextDTO | None = None
