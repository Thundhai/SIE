"""Tests for `HseExpertReview` (model) and
`app/services/hse_review_service.py` — Real Enterprise Dataset
Validation Foundation v0.1, item 8.

Runs against `db_session` (SQLite) — plain CRUD/tenant-scoping only, no
temporal comparisons that would need real PostgreSQL.
"""

import uuid

import pytest

from app.models.organization import Organization
from app.services import hse_review_service


def _make_org(db_session, name: str) -> uuid.UUID:
    org = Organization(name=name)
    db_session.add(org)
    db_session.commit()
    return org.id


# --- Basic lifecycle -------------------------------------------------------------------------


def test_queue_for_review_creates_a_pending_row(db_session):
    org_id = _make_org(db_session, "HSE Review Org A")
    review = hse_review_service.queue_for_review(
        db_session, organization_id=org_id, target_type="TERMINOLOGY_MAPPING",
        target_reference="event_type::finding", provenance={"reason": "AMBIGUOUS"},
    )
    assert review.outcome is None
    assert review.reviewed_at is None
    assert review.provenance == {"reason": "AMBIGUOUS"}


def test_queue_for_review_rejects_unknown_target_type(db_session):
    org_id = _make_org(db_session, "HSE Review Org B")
    with pytest.raises(ValueError):
        hse_review_service.queue_for_review(
            db_session, organization_id=org_id, target_type="NOT_A_REAL_TYPE", target_reference="x"
        )


def test_submit_review_records_outcome_comment_and_timestamp(db_session):
    org_id = _make_org(db_session, "HSE Review Org C")
    review = hse_review_service.queue_for_review(
        db_session, organization_id=org_id, target_type="QUARANTINED_RECORD", target_reference="evt-123"
    )
    updated = hse_review_service.submit_review(
        db_session, organization_id=org_id, review_id=review.id, outcome="INCORRECT",
        reviewer_comment="This should have mapped to NEAR_MISS.",
    )
    assert updated.outcome == "INCORRECT"
    assert updated.reviewer_comment == "This should have mapped to NEAR_MISS."
    assert updated.reviewed_at is not None


def test_submit_review_rejects_an_unknown_outcome(db_session):
    org_id = _make_org(db_session, "HSE Review Org D")
    review = hse_review_service.queue_for_review(
        db_session, organization_id=org_id, target_type="RISK_INDICATOR", target_reference="signal-x"
    )
    with pytest.raises(ValueError):
        hse_review_service.submit_review(db_session, organization_id=org_id, review_id=review.id, outcome="MAYBE")


def test_list_reviews_pending_only_excludes_reviewed_rows(db_session):
    org_id = _make_org(db_session, "HSE Review Org E")
    r1 = hse_review_service.queue_for_review(
        db_session, organization_id=org_id, target_type="CLASSIFICATION", target_reference="a"
    )
    hse_review_service.queue_for_review(db_session, organization_id=org_id, target_type="CLASSIFICATION", target_reference="b")
    hse_review_service.submit_review(db_session, organization_id=org_id, review_id=r1.id, outcome="CORRECT")

    pending = hse_review_service.list_reviews(db_session, organization_id=org_id, pending_only=True)
    assert len(pending) == 1
    assert pending[0].target_reference == "b"

    all_reviews = hse_review_service.list_reviews(db_session, organization_id=org_id)
    assert len(all_reviews) == 2


def test_list_reviews_filters_by_target_type(db_session):
    org_id = _make_org(db_session, "HSE Review Org F")
    hse_review_service.queue_for_review(db_session, organization_id=org_id, target_type="TERMINOLOGY_MAPPING", target_reference="a")
    hse_review_service.queue_for_review(db_session, organization_id=org_id, target_type="RISK_INDICATOR", target_reference="b")
    only_terminology = hse_review_service.list_reviews(db_session, organization_id=org_id, target_type="TERMINOLOGY_MAPPING")
    assert len(only_terminology) == 1
    assert only_terminology[0].target_type == "TERMINOLOGY_MAPPING"


# --- Tenant isolation -------------------------------------------------------------------------


def test_reviews_are_isolated_between_organizations(db_session):
    org_a = _make_org(db_session, "HSE Review Tenant A")
    org_b = _make_org(db_session, "HSE Review Tenant B")
    hse_review_service.queue_for_review(db_session, organization_id=org_a, target_type="CLASSIFICATION", target_reference="a")
    hse_review_service.queue_for_review(db_session, organization_id=org_b, target_type="CLASSIFICATION", target_reference="b")

    assert len(hse_review_service.list_reviews(db_session, organization_id=org_a)) == 1
    assert len(hse_review_service.list_reviews(db_session, organization_id=org_b)) == 1


def test_submit_review_on_another_organizations_review_returns_none_never_raises(db_session):
    org_a = _make_org(db_session, "HSE Review Tenant C")
    org_b = _make_org(db_session, "HSE Review Tenant D")
    review = hse_review_service.queue_for_review(db_session, organization_id=org_a, target_type="CLASSIFICATION", target_reference="a")

    result = hse_review_service.submit_review(db_session, organization_id=org_b, review_id=review.id, outcome="CORRECT")
    assert result is None

    # The review itself is untouched -- still pending, under its real organization.
    still_pending = hse_review_service.list_reviews(db_session, organization_id=org_a, pending_only=True)
    assert len(still_pending) == 1


# --- Never an automated approval workflow -----------------------------------------------------


def test_this_is_evaluation_only_review_outcome_is_never_read_by_ingestion_or_mapping():
    """A structural guarantee, not a runtime one: `app/intelligence/terminology_mapping.py`
    and `app/intelligence/enterprise_ingestion.py` (the actual ingestion/mapping
    pipeline) must never import from `app.services.hse_review_service` or
    `app.models.hse_expert_review` -- this review mechanism has no way to
    feed back into automated decisions."""
    import app.intelligence.enterprise_ingestion as ingestion_module
    import app.intelligence.terminology_mapping as mapping_module

    assert "hse_review_service" not in vars(ingestion_module)
    assert "hse_expert_review" not in vars(ingestion_module)
    assert "hse_review_service" not in vars(mapping_module)
    assert "hse_expert_review" not in vars(mapping_module)
