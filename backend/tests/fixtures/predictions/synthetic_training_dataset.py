"""Synthetic predictive-modeling training dataset — milestone item 39.

Directly persists `SafetyEvent` rows (unlike
`tests/fixtures/intelligence/synthetic_dataset.py`, which builds
`RawSafetyEventPayload`s for exercising the ingestion pipeline — this
fixture exists one layer downstream of that, to exercise dataset
construction/training/evaluation, so it writes rows straight into the
database via `tests.intelligence_test_helpers.make_safety_event`).

**Explicitly NOT a claim about real-world predictive performance**
(milestone item 39's own instruction, and `app/predictions/training.py`'s
own `PROTOTYPE_MODEL_LABEL`). This dataset exists only to prove the
pipeline — dataset construction, temporal splitting, model fitting,
evaluation, registration, prediction, backtesting — works correctly
end to end on data with a *known, deliberately engineered* structure
(a genuine regime change in incident risk), not to produce a model
anyone should trust as safety intelligence.

    seed_synthetic_organization(db, name=..., site_names=[...], seed=...)
        -> (Organization, [Site, ...])
        -> ~2 years of NEAR_MISS/OBSERVATION/INCIDENT events per site,
           with a deliberate LOW -> ELEVATED -> LOW risk regime change
           (the "changing risk patterns" the milestone item asks for)

Two organizations (`seed_two_organization_dataset()`) so every test that
needs cross-tenant data (milestone item 43) can use this fixture too,
never a second bespoke org-building helper.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.site import Site
from tests.intelligence_test_helpers import make_safety_event

DEFAULT_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEFAULT_NUM_DAYS = 730  # ~2 years -- item 39's "multiple years"
DEFAULT_EVENT_STRIDE_DAYS = 2  # an event opportunity every other day


def _risk_regime(day: int, num_days: int) -> float:
    """LOW -> ELEVATED -> LOW incident probability across the dataset's
    span -- a deliberate, known regime change (milestone item 39), not a
    flat/stationary process a model could trivially "solve" by memorizing
    a single base rate."""
    third = num_days / 3
    if third <= day < 2 * third:
        return 0.14
    return 0.03


def seed_synthetic_organization(
    db: Session,
    *,
    name: str,
    site_names: list[str],
    seed: int,
    start: datetime = DEFAULT_START,
    num_days: int = DEFAULT_NUM_DAYS,
    stride_days: int = DEFAULT_EVENT_STRIDE_DAYS,
) -> tuple[Organization, list[Site]]:
    rng = random.Random(seed)

    org = Organization(name=name)
    db.add(org)
    db.commit()

    sites = [Site(organization_id=org.id, name=site_name) for site_name in site_names]
    db.add_all(sites)
    db.commit()

    for site in sites:
        for day in range(0, num_days, stride_days):
            t = start + timedelta(days=day)

            # Leading indicators -- reporting activity, correlated with
            # (but never identical to) the underlying regime; see
            # app/predictions/spec.py item 5's reporting-bias note.
            near_miss_p = 0.25 + (0.2 if _risk_regime(day, num_days) > 0.1 else 0.0)
            if rng.random() < near_miss_p:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
                        event_time=t, ingestion_time=t,
                        severity=rng.choice(["LOW", "MEDIUM"]),
                    )
                )
            if rng.random() < 0.2:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="OBSERVATION",
                        event_time=t, ingestion_time=t,
                    )
                )
            if rng.random() < 0.15:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="CORRECTIVE_ACTION",
                        event_time=t, ingestion_time=t,
                        status=rng.choice(["OPEN", "OVERDUE", "CLOSED"]),
                    )
                )
            if rng.random() < 0.1:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="EQUIPMENT",
                        event_subtype=rng.choice(["failure", "inspection", "maintenance"]),
                        event_time=t, ingestion_time=t,
                        status=rng.choice(["OPEN", "OVERDUE", "CLOSED"]),
                    )
                )
            if rng.random() < 0.1:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="TRAINING",
                        event_time=t, ingestion_time=t,
                        status=rng.choice(["COMPLETED", "OVERDUE", "EXPIRED"]),
                    )
                )

            # The target itself: INCIDENT probability follows the
            # regime -- this is what a working pipeline should be able to
            # (weakly) pick up on via the leading-indicator features.
            if rng.random() < _risk_regime(day, num_days):
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="INCIDENT",
                        event_time=t, ingestion_time=t, data_quality_status="VALID",
                        severity=rng.choice(["LOW", "MEDIUM", "HIGH"]),
                    )
                )

            if day % 30 == 0:
                db.commit()
        db.commit()

    return org, sites


def seed_two_organization_dataset(
    db: Session, *, seed: int = 1234
) -> tuple[tuple[Organization, list[Site]], tuple[Organization, list[Site]]]:
    """Two independently-seeded organizations, each with two sites — the
    minimum shape milestone item 43's cross-tenant test needs (org A's
    training/prediction pipeline must never see org B's events)."""
    org_a = seed_synthetic_organization(
        db, name=f"Synthetic Org A {uuid.uuid4().hex[:8]}", site_names=["Site A1", "Site A2"], seed=seed,
    )
    org_b = seed_synthetic_organization(
        db, name=f"Synthetic Org B {uuid.uuid4().hex[:8]}", site_names=["Site B1"], seed=seed + 1,
    )
    return org_a, org_b


def as_of_dates(
    *, start: datetime = DEFAULT_START, num_days: int = DEFAULT_NUM_DAYS, warmup_days: int = 60, cadence_days: int = 15
) -> list[datetime]:
    """A deterministic, evenly-spaced series of `as_of` dates spanning
    the seeded dataset — `warmup_days` skipped at the start so every
    `as_of` has at least that much historical data to build a feature
    snapshot from, and enough trailing room left for the horizon (see
    `app/predictions/spec.py::HORIZON_DAYS`) to actually resolve within
    the seeded span."""
    return [start + timedelta(days=d) for d in range(warmup_days, num_days - 60, cadence_days)]
