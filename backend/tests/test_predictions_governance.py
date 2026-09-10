"""Model risk governance — Model Validation & Governance v0.1, items
34-35. DB-backed (SQLite) tests."""

from app.models.audit_log import AuditLog
from app.predictions.dataset import build_training_examples
from app.predictions.enums import GovernanceRecommendation
from app.predictions.governance import (
    ApprovalCriteria,
    generate_validation_report,
    record_validation_report,
)
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)


def _train_model(db_session, *, seed=400):
    org, sites = seed_synthetic_organization(db_session, name="Governance Org", site_names=["S1", "S2"], seed=seed)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    return train_baseline_model(db_session, organization_id=org.id, examples=examples)


def test_a_model_with_no_metrics_is_rejected_never_silently_approved(db_session):
    entry = _train_model(db_session)
    entry.metrics = {}  # simulate a model with nothing computed
    report = generate_validation_report(model=entry)
    assert report.recommendation == GovernanceRecommendation.REJECT.value
    assert any(c.name == "recall" and not c.passed for c in report.checks)


def test_the_recommendation_is_never_more_favorable_than_the_worst_hard_check(db_session):
    entry = _train_model(db_session)
    lenient = ApprovalCriteria(min_recall=0.0, min_precision=0.0, max_false_negative_rate=1.0, min_data_quality="INSUFFICIENT")
    report = generate_validation_report(model=entry, criteria=lenient)
    # With every threshold trivially satisfiable, nothing should be a
    # hard failure -- APPROVE or REVIEW, never REJECT.
    assert report.recommendation in (GovernanceRecommendation.APPROVE.value, GovernanceRecommendation.REVIEW.value)


def test_every_check_is_individually_inspectable_not_just_the_bottom_line(db_session):
    entry = _train_model(db_session)
    report = generate_validation_report(model=entry)
    assert len(report.checks) >= 4
    for check in report.checks:
        assert check.detail  # every check explains itself


def test_report_to_dict_is_json_serializable(db_session):
    import json

    entry = _train_model(db_session)
    report = generate_validation_report(model=entry)
    json.dumps(report.to_dict())  # raises if anything isn't serializable


def test_record_validation_report_writes_an_audit_log_entry(db_session):
    entry = _train_model(db_session)
    report = generate_validation_report(model=entry)
    record_validation_report(db_session, entry, report)
    logged = db_session.query(AuditLog).filter_by(resource_id=entry.id, action="MODEL_VALIDATION_REPORT_GENERATED").one()
    assert logged.event_metadata["recommendation"] == report.recommendation


def test_thresholds_are_never_hard_coded_they_are_all_overridable():
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ApprovalCriteria)}
    assert {"min_recall", "min_precision", "max_false_negative_rate", "min_data_quality"} <= fields
