"""Model risk governance — Model Validation & Governance v0.1, items
34-35.

    ModelRegistryEntry (test-split metrics already computed at training time)
        + DatasetVersion (optional -- its own quality report)
        + FeatureDriftReport / DataDriftResult (optional)
        + StabilityReport (optional)
        -> generate_validation_report()
        -> ValidationReport(recommendation=APPROVE | REJECT | REVIEW, reasons=[...])

**The recommendation is exactly that — a recommendation, never a
decision this module makes itself.** `app/predictions/model_registry.py::approve()`/
`reject()` still require an explicit, separate `reviewer_user_id` call
(milestone item 23); nothing here transitions a model's status. A human
reviewer reads this report — every individual check, not just the
bottom line — and decides.

**"INITIAL GOVERNANCE DEFAULT" (item 35's own required label).** Every
threshold on `ApprovalCriteria` is a documented starting point this
codebase has not validated against real-world outcomes; a caller may
(and, before any real deployment, should) supply its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.dataset_version import DatasetVersion
from app.models.model_registry_entry import ModelRegistryEntry
from app.predictions.drift import DataDriftResult, FeatureDriftReport
from app.predictions.enums import GovernanceRecommendation
from app.predictions.stability import StabilityReport, summarize_variability
from app.services.audit_service import AuditAction, audit_service

# --- INITIAL GOVERNANCE DEFAULT (item 35) -----------------------------------------------
DEFAULT_MIN_RECALL = 0.5
DEFAULT_MIN_PRECISION = 0.15
DEFAULT_MAX_FALSE_NEGATIVE_RATE = 0.5
DEFAULT_MAX_RECALL_VARIABILITY_STDEV = 0.35
_DATA_QUALITY_RANK = {"GOOD": 3, "LIMITED": 2, "INSUFFICIENT": 1, "UNKNOWN": 0}
DEFAULT_MIN_DATA_QUALITY = "LIMITED"

# Below this fraction of the minimum, a check is a REJECT-grade failure
# rather than a REVIEW-grade one -- see _classify() below.
_HARD_FAILURE_MARGIN = 0.5


@dataclass
class ApprovalCriteria:
    """INITIAL GOVERNANCE DEFAULT — see module docstring."""

    min_recall: float = DEFAULT_MIN_RECALL
    min_precision: float = DEFAULT_MIN_PRECISION
    max_false_negative_rate: float = DEFAULT_MAX_FALSE_NEGATIVE_RATE
    max_recall_variability_stdev: float = DEFAULT_MAX_RECALL_VARIABILITY_STDEV
    min_data_quality: str = DEFAULT_MIN_DATA_QUALITY


@dataclass
class GovernanceCheck:
    name: str
    passed: bool
    severity: str  # "hard" | "soft" -- hard failures push toward REJECT, soft ones toward REVIEW
    detail: str


@dataclass
class ValidationReport:
    model_id: uuid.UUID
    model_name: str
    model_version: str
    model_type: str
    prediction_target_version: str
    feature_set_version: str
    dataset_version_id: uuid.UUID | None
    dataset_environment: str | None

    recall: float | None
    precision: float | None
    pr_auc: float | None
    roc_auc: float | None
    false_negative_rate: float | None
    calibration_validated: bool
    data_quality: str

    drift_summary: dict | None
    stability_summary: dict | None

    checks: list[GovernanceCheck] = field(default_factory=list)
    recommendation: str = GovernanceRecommendation.REVIEW.value
    criteria_used: ApprovalCriteria = field(default_factory=ApprovalCriteria)

    def to_dict(self) -> dict:
        return {
            "model_id": str(self.model_id),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "prediction_target_version": self.prediction_target_version,
            "feature_set_version": self.feature_set_version,
            "dataset_version_id": str(self.dataset_version_id) if self.dataset_version_id else None,
            "dataset_environment": self.dataset_environment,
            "recall": self.recall,
            "precision": self.precision,
            "pr_auc": self.pr_auc,
            "roc_auc": self.roc_auc,
            "false_negative_rate": self.false_negative_rate,
            "calibration_validated": self.calibration_validated,
            "data_quality": self.data_quality,
            "drift_summary": self.drift_summary,
            "stability_summary": self.stability_summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "severity": c.severity, "detail": c.detail} for c in self.checks
            ],
            "recommendation": self.recommendation,
        }


def _check(name: str, passed: bool, severity: str, detail: str) -> GovernanceCheck:
    return GovernanceCheck(name=name, passed=passed, severity=severity, detail=detail)


def generate_validation_report(
    *,
    model: ModelRegistryEntry,
    dataset_version: DatasetVersion | None = None,
    feature_drift: FeatureDriftReport | None = None,
    data_drift: DataDriftResult | None = None,
    stability: StabilityReport | None = None,
    criteria: ApprovalCriteria | None = None,
) -> ValidationReport:
    criteria = criteria or ApprovalCriteria()

    test_overall = (model.metrics or {}).get("test", {}).get("overall", {})
    recall = test_overall.get("recall")
    precision = test_overall.get("precision")
    pr_auc = test_overall.get("pr_auc")
    roc_auc = test_overall.get("roc_auc")
    false_negative_rate = (1 - recall) if recall is not None else None

    data_quality = "UNKNOWN"
    if dataset_version is not None:
        data_quality = (dataset_version.quality_report or {}).get("overall_quality", "UNKNOWN")

    checks: list[GovernanceCheck] = []

    if recall is None:
        checks.append(_check("recall", False, "hard", "No recall metric available -- the model cannot be evaluated at all."))
    else:
        checks.append(
            _check(
                "recall", recall >= criteria.min_recall,
                "hard" if recall < criteria.min_recall * _HARD_FAILURE_MARGIN else "soft",
                f"Recall {recall:.4f} vs required {criteria.min_recall}.",
            )
        )

    if precision is None:
        checks.append(_check("precision", False, "soft", "No precision metric available."))
    else:
        checks.append(
            _check(
                "precision", precision >= criteria.min_precision,
                "soft",
                f"Precision {precision:.4f} vs required {criteria.min_precision}.",
            )
        )

    if false_negative_rate is None:
        checks.append(_check("false_negative_rate", False, "hard", "False-negative rate could not be computed (no recall)."))
    else:
        checks.append(
            _check(
                "false_negative_rate", false_negative_rate <= criteria.max_false_negative_rate,
                "hard" if false_negative_rate > min(1.0, criteria.max_false_negative_rate + _HARD_FAILURE_MARGIN) else "soft",
                f"False-negative rate {false_negative_rate:.4f} vs max {criteria.max_false_negative_rate}.",
            )
        )

    checks.append(
        _check(
            "data_quality",
            _DATA_QUALITY_RANK.get(data_quality, 0) >= _DATA_QUALITY_RANK[criteria.min_data_quality],
            "hard" if data_quality == "INSUFFICIENT" else "soft",
            f"Dataset overall_quality={data_quality!r} vs minimum {criteria.min_data_quality!r}.",
        )
    )

    drift_summary = None
    if feature_drift is not None:
        shifted = feature_drift.shifted_features
        drift_summary = {"shifted_feature_count": len(shifted), "shifted_features": [f.feature_name for f in shifted]}
        checks.append(
            _check(
                "feature_drift", len(shifted) == 0, "soft",
                f"{len(shifted)} feature(s) show moderate/significant drift vs training baseline." if shifted else "No feature drift detected.",
            )
        )
    if data_drift is not None:
        drift_summary = drift_summary or {}
        drift_summary["data_drift_status"] = data_drift.status
        checks.append(
            _check("data_drift", data_drift.status != "SHIFTED", "soft", f"Event-frequency data drift status: {data_drift.status}.")
        )

    stability_summary = None
    if stability is not None:
        variability = summarize_variability(stability, metric_name="recall")
        stability_summary = {
            "dimension": stability.dimension, "recall_mean": variability.mean, "recall_stdev": variability.stdev,
        }
        if variability.stdev is not None:
            checks.append(
                _check(
                    "stability", variability.stdev <= criteria.max_recall_variability_stdev, "soft",
                    f"Recall stdev across {stability.dimension} slices: {variability.stdev:.4f} vs max {criteria.max_recall_variability_stdev}.",
                )
            )

    recommendation = _classify(checks)

    return ValidationReport(
        model_id=model.id,
        model_name=model.model_name,
        model_version=model.model_version,
        model_type=model.model_type,
        prediction_target_version=model.prediction_target_version,
        feature_set_version=model.feature_set_version,
        dataset_version_id=model.dataset_version_id,
        dataset_environment=dataset_version.environment if dataset_version is not None else None,
        recall=recall, precision=precision, pr_auc=pr_auc, roc_auc=roc_auc,
        false_negative_rate=false_negative_rate,
        calibration_validated=model.calibration_validated,
        data_quality=data_quality,
        drift_summary=drift_summary,
        stability_summary=stability_summary,
        checks=checks,
        recommendation=recommendation,
        criteria_used=criteria,
    )


def _classify(checks: list[GovernanceCheck]) -> str:
    hard_failures = [c for c in checks if c.severity == "hard" and not c.passed]
    soft_failures = [c for c in checks if c.severity == "soft" and not c.passed]
    if hard_failures:
        return GovernanceRecommendation.REJECT.value
    if soft_failures:
        return GovernanceRecommendation.REVIEW.value
    return GovernanceRecommendation.APPROVE.value


def record_validation_report(db: Session, model: ModelRegistryEntry, report: ValidationReport) -> None:
    """Audit-logs the report (never silently discarded) — does NOT
    transition the model's status; see module docstring."""
    audit_service.log(
        db,
        action=AuditAction.MODEL_VALIDATION_REPORT_GENERATED,
        resource_type="model_registry_entry",
        resource_id=model.id,
        organization_id=model.organization_id,
        metadata={"recommendation": report.recommendation, "checks": [c.name for c in report.checks if not c.passed]},
    )


__all__ = [
    "DEFAULT_MAX_FALSE_NEGATIVE_RATE",
    "DEFAULT_MAX_RECALL_VARIABILITY_STDEV",
    "DEFAULT_MIN_DATA_QUALITY",
    "DEFAULT_MIN_PRECISION",
    "DEFAULT_MIN_RECALL",
    "ApprovalCriteria",
    "GovernanceCheck",
    "ValidationReport",
    "generate_validation_report",
    "record_validation_report",
]
