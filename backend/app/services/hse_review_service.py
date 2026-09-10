"""HSE expert review service — the one write/read path for
`HseExpertReview` rows (see that model's own docstring for what this is
and, more importantly, what it is not: an evaluation mechanism only,
never an automated safety-approval workflow — nothing here changes
ingestion, mapping, or intelligence behavior based on a review outcome).

    queue_for_review(...)   -- create a pending row (outcome=None)
    submit_review(...)      -- a human's judgment, once given
    list_reviews(...)       -- the review queue / history, tenant-scoped

Every function is tenant-scoped by `organization_id` — there is no
cross-organization read or write path here, exactly the same rule every
other resource in this codebase already follows.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hse_expert_review import REVIEW_OUTCOMES, TARGET_TYPES, HseExpertReview


def queue_for_review(
    db: Session,
    *,
    organization_id: uuid.UUID,
    target_type: str,
    target_reference: str,
    provenance: dict[str, Any] | None = None,
) -> HseExpertReview:
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown target_type {target_type!r}. Supported: {TARGET_TYPES}")
    review = HseExpertReview(
        organization_id=organization_id,
        target_type=target_type,
        target_reference=target_reference,
        provenance=provenance or {},
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def submit_review(
    db: Session,
    *,
    organization_id: uuid.UUID,
    review_id: uuid.UUID,
    outcome: str,
    reviewer_comment: str | None = None,
    reviewer_user_id: uuid.UUID | None = None,
) -> HseExpertReview | None:
    """Returns `None` (never raises) for a review that doesn't exist or
    doesn't belong to `organization_id` — tenant isolation preserved the
    same way every other service in this codebase handles a
    not-found-or-not-yours lookup."""
    if outcome not in REVIEW_OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r}. Supported: {REVIEW_OUTCOMES}")
    review = db.execute(
        select(HseExpertReview).where(
            HseExpertReview.id == review_id, HseExpertReview.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if review is None:
        return None
    review.outcome = outcome
    review.reviewer_comment = reviewer_comment
    review.reviewer_user_id = reviewer_user_id
    review.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)
    return review


def list_reviews(
    db: Session,
    *,
    organization_id: uuid.UUID,
    target_type: str | None = None,
    pending_only: bool = False,
) -> list[HseExpertReview]:
    query = select(HseExpertReview).where(HseExpertReview.organization_id == organization_id)
    if target_type is not None:
        query = query.where(HseExpertReview.target_type == target_type)
    if pending_only:
        query = query.where(HseExpertReview.outcome.is_(None))
    query = query.order_by(HseExpertReview.created_at)
    return list(db.execute(query).scalars().all())
