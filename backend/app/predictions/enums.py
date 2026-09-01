"""Enumerations for the predictive risk modeling domain. Mirrors
`app/intelligence/enums.py`'s own stated philosophy: only closed
vocabularies become enums here; the database columns backing them stay
plain `String` (see `app/models/prediction.py`/`model_registry_entry.py`).
"""

from enum import Enum


class ModelStatus(str, Enum):
    """The model lifecycle (milestone items 25-26). Training only ever
    produces `TRAINED`; every later transition is a deliberate, separate
    call (`app/predictions/model_registry.py`) — nothing auto-promotes a
    model. `RETIRED`/`REJECTED` are terminal."""

    TRAINED = "TRAINED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


# Transitions a human/service call may make -- see model_registry.py.
# Anything not listed here is refused. DEPLOYED -> APPROVED is the
# "undeploy" transition (Model Validation & Governance v0.1, item 25) --
# it returns to APPROVED rather than RETIRED so an undeployed model can
# be redeployed later (model_registry.py::deploy()) without needing to
# pass back through VALIDATED review; DEPLOYED -> RETIRED remains the
# permanent decommission path. Both are still human-invoked, audited
# calls -- neither ever fires on its own.
_ALLOWED_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    ModelStatus.TRAINED: frozenset({ModelStatus.VALIDATED, ModelStatus.REJECTED}),
    ModelStatus.VALIDATED: frozenset({ModelStatus.APPROVED, ModelStatus.REJECTED}),
    ModelStatus.APPROVED: frozenset({ModelStatus.DEPLOYED, ModelStatus.REJECTED}),
    ModelStatus.DEPLOYED: frozenset({ModelStatus.RETIRED, ModelStatus.APPROVED}),
    ModelStatus.RETIRED: frozenset(),
    ModelStatus.REJECTED: frozenset(),
}


def is_allowed_transition(current: str, target: str) -> bool:
    try:
        return ModelStatus(target) in _ALLOWED_TRANSITIONS[ModelStatus(current)]
    except ValueError:
        return False


class RiskCategory(str, Enum):
    """Never a fabricated probability (milestone items 18-19) — this is
    the vocabulary used until/unless a model's calibration has actually
    been validated (`ModelRegistryEntry.calibration_validated`)."""

    ELEVATED = "ELEVATED"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PredictionOutcome(str, Enum):
    PREDICTED = "PREDICTED"
    NO_PREDICTION = "NO_PREDICTION"


class AbstentionReason(str, Enum):
    """Milestone item 30's own list, verbatim."""

    INSUFFICIENT_HISTORICAL_DATA = "INSUFFICIENT_HISTORICAL_DATA"
    STALE_SOURCE_DATA = "STALE_SOURCE_DATA"
    REQUIRED_FEATURES_MISSING = "REQUIRED_FEATURES_MISSING"
    UNSUPPORTED_ENTITY = "UNSUPPORTED_ENTITY"
    MODEL_NOT_VALIDATED = "MODEL_NOT_VALIDATED"
    MODEL_NOT_APPROVED = "MODEL_NOT_APPROVED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    COLD_START = "COLD_START"
    # Model Validation & Governance v0.1, item 24: the deployment gate
    # also checks that the serving model's own feature-set/target
    # version still matches what app/predictions/spec.py currently
    # declares -- a model trained against a since-superseded feature set
    # or target definition must never silently keep serving.
    MODEL_VERSION_INCOMPATIBLE = "MODEL_VERSION_INCOMPATIBLE"


class PredictionDataQuality(str, Enum):
    """Milestone item 29 — deliberately a distinct vocabulary from
    `app.intelligence.enums.DataSufficiency` (which grades whether a
    *feature* has enough underlying events): this grades the
    trustworthiness of a *prediction* as a whole, including source
    freshness, which `DataSufficiency` does not consider at all."""

    GOOD = "GOOD"
    LIMITED = "LIMITED"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"


class DatasetEnvironment(str, Enum):
    """Milestone item 3 (Model Validation & Governance v0.1) — the one
    tag that must never be conflated: a `DatasetVersion` (and every
    report/model built from it) is either genuinely synthetic test data
    or genuinely real organizational data, never silently either."""

    SYNTHETIC = "SYNTHETIC"
    REAL = "REAL"


class ModelValidationStatus(str, Enum):
    """Milestone item 7 — whether a dataset even has enough data to
    attempt training/validation at all, checked *before* any model is
    fit. `SUFFICIENT` is not a claim the resulting model will perform
    well, only that there is enough data to responsibly try."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ProbabilityStatus(str, Enum):
    """Milestone item 14 — whether a model's raw score has actually been
    checked against real observed frequencies and found well-calibrated.
    Mirrors `ModelRegistryEntry.calibration_validated`
    (`CALIBRATED` <-> `True`), but as an explicit, inspectable status
    string rather than a bare boolean, so an API response can say
    *why* a probability is or isn't being shown."""

    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"


class GovernanceRecommendation(str, Enum):
    """Milestone item 34 — the validation report's own recommendation.
    Deliberately distinct from `ModelStatus`: this is what
    `app/predictions/governance.py` *suggests*, based on the complete
    evidence (data quality, metrics, calibration, false-negative rate,
    drift, stability) — a human reviewer still makes the actual
    `model_registry.py::approve()`/`reject()` call (milestone item 23);
    nothing auto-applies this recommendation."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class ReviewFlagStatus(str, Enum):
    """`ModelReviewFlag.status` — milestone items 31-32."""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class ReviewFlagReason(str, Enum):
    """`ModelReviewFlag.reason` — what kind of drift/degradation
    triggered a `MODEL_REVIEW_REQUIRED` flag (milestone items 29-31)."""

    PERFORMANCE_DRIFT = "PERFORMANCE_DRIFT"
    FEATURE_DRIFT = "FEATURE_DRIFT"
    DATA_DRIFT = "DATA_DRIFT"
