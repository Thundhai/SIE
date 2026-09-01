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
# Anything not listed here is refused.
_ALLOWED_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    ModelStatus.TRAINED: frozenset({ModelStatus.VALIDATED, ModelStatus.REJECTED}),
    ModelStatus.VALIDATED: frozenset({ModelStatus.APPROVED, ModelStatus.REJECTED}),
    ModelStatus.APPROVED: frozenset({ModelStatus.DEPLOYED, ModelStatus.REJECTED}),
    ModelStatus.DEPLOYED: frozenset({ModelStatus.RETIRED}),
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
