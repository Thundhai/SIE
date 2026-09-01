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

**Explicit evaluation scenarios (Model Validation & Governance v0.1,
item 42 — "never an unrealistically perfect synthetic dataset").**
`seed_synthetic_organization()` above is one scenario (a genuine regime
change); the module also exposes these named scenarios, each a thin
wrapper over the same event-generation engine with a different
`risk_fn`/reporting/leading-indicator/deterioration shape so every test
that needs one doesn't hand-roll its own generator:

    seed_stable_organization(...)                                -> flat incident risk, no regime change
    seed_increasing_risk_organization(...)                       -> risk rises across the whole window
    seed_decreasing_risk_organization(...)                       -> risk falls across the whole window
    seed_sparse_data_organization(...)                           -> few sites, long stride, short window
    seed_stale_data_organization(..., stale_gap_days=...)        -> events stop well before the declared date range ends
    seed_reporting_bias_organization(...)                        -> reporting volume drops independent of actual risk
    seed_equipment_failure_leading_indicator_organization(...)   -> EQUIPMENT events cluster ahead of the elevated-risk period
    seed_corrective_action_deterioration_organization(...)       -> corrective actions increasingly OPEN/OVERDUE as risk rises
    seed_training_deterioration_organization(...)                -> training compliance increasingly OVERDUE/EXPIRED as risk rises

None of these is a claim about a real organization's actual risk pattern
— each is a deliberately engineered, documented shape used to prove a
specific piece of the validation/governance pipeline (drift detection,
stability analysis, reporting-bias-vs-real-risk distinction, leading
indicators, calibration) behaves correctly on data with that known
structure, never to claim the resulting model is production-accurate.
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
    a single base rate. This is `seed_synthetic_organization()`'s own
    default `risk_fn` -- see the other named `_*_risk_regime` functions
    below for the additional scenarios item 42 asks for."""
    third = num_days / 3
    if third <= day < 2 * third:
        return 0.14
    return 0.03


def _stable_risk_regime(day: int, num_days: int) -> float:
    """A flat incident base rate -- no regime change at all, the
    counterpoint to `_risk_regime()`'s deliberate shift (item 42's
    "stable period")."""
    return 0.06


def _increasing_risk_regime(day: int, num_days: int) -> float:
    """Risk rises steadily across the whole window (item 42's
    "increasing-risk period")."""
    return 0.02 + 0.16 * (day / max(num_days - 1, 1))


def _decreasing_risk_regime(day: int, num_days: int) -> float:
    """Risk falls steadily across the whole window (item 42's
    "decreasing-risk period")."""
    return 0.18 - 0.16 * (day / max(num_days - 1, 1))


def seed_synthetic_organization(
    db: Session,
    *,
    name: str,
    site_names: list[str],
    seed: int,
    start: datetime = DEFAULT_START,
    num_days: int = DEFAULT_NUM_DAYS,
    stride_days: int = DEFAULT_EVENT_STRIDE_DAYS,
    risk_fn=_risk_regime,
    reporting_multiplier_fn=None,
    equipment_leading: bool = False,
    equipment_lead_days: int = 14,
    corrective_action_deterioration: bool = False,
    training_deterioration: bool = False,
    stop_after_days: int | None = None,
) -> tuple[Organization, list[Site]]:
    """The one event-generation engine every named scenario in this
    module (see module docstring) is built from.

    `risk_fn(day, num_days) -> float` decides the INCIDENT probability
    curve -- swap it to get a stable/increasing/decreasing/regime-change
    dataset without duplicating the generator. `reporting_multiplier_fn`
    (if given) scales NEAR_MISS/OBSERVATION reporting volume independent
    of `risk_fn`, for the reporting-bias scenario (a change in how much
    gets reported is not the same thing as a change in actual risk --
    item 42's "reporting-bias scenario", and a model/report that
    confuses the two is exactly what stability/drift analysis here
    should catch). `equipment_leading` makes EQUIPMENT failure reports
    anticipate an elevated-risk period by `equipment_lead_days` (a real
    leading indicator). `corrective_action_deterioration`/
    `training_deterioration` shift each domain's own status mix toward
    OPEN/OVERDUE/EXPIRED as `day` advances. `stop_after_days` (if given)
    stops emitting events at that day, leaving the remainder of
    `[start, start + num_days)` deliberately empty -- the stale-data
    scenario, simulating an ingestion pipeline that stopped feeding
    fresh data partway through the dataset's declared range.
    """
    rng = random.Random(seed)

    org = Organization(name=name)
    db.add(org)
    db.commit()

    sites = [Site(organization_id=org.id, name=site_name) for site_name in site_names]
    db.add_all(sites)
    db.commit()

    event_horizon = num_days if stop_after_days is None else stop_after_days

    for site in sites:
        for day in range(0, event_horizon, stride_days):
            t = start + timedelta(days=day)
            regime_elevated = risk_fn(day, num_days) > 0.1

            # Leading indicators -- reporting activity, correlated with
            # (but never identical to) the underlying regime; see
            # app/predictions/spec.py item 5's reporting-bias note.
            near_miss_p = 0.25 + (0.2 if regime_elevated else 0.0)
            observation_p = 0.2
            if reporting_multiplier_fn is not None:
                multiplier = reporting_multiplier_fn(day, num_days)
                near_miss_p = min(1.0, near_miss_p * multiplier)
                observation_p = min(1.0, observation_p * multiplier)

            if rng.random() < near_miss_p:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="NEAR_MISS",
                        event_time=t, ingestion_time=t,
                        severity=rng.choice(["LOW", "MEDIUM"]),
                    )
                )
            if rng.random() < observation_p:
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="OBSERVATION",
                        event_time=t, ingestion_time=t,
                    )
                )
            if rng.random() < 0.15:
                if corrective_action_deterioration:
                    overdue_share = 0.15 + 0.55 * (day / max(num_days - 1, 1))
                    status = rng.choices(
                        ["CLOSED", "OPEN", "OVERDUE"],
                        weights=[max(0.05, 1 - overdue_share), overdue_share * 0.5, overdue_share * 0.5],
                    )[0]
                else:
                    status = rng.choice(["OPEN", "OVERDUE", "CLOSED"])
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="CORRECTIVE_ACTION",
                        event_time=t, ingestion_time=t,
                        status=status,
                    )
                )

            if equipment_leading:
                lead_day = min(day + equipment_lead_days, num_days - 1)
                lead_elevated = risk_fn(lead_day, num_days) > 0.1
                equipment_p = 0.08 + (0.3 if lead_elevated else 0.0)
            else:
                lead_elevated = False
                equipment_p = 0.1
            if rng.random() < equipment_p:
                if equipment_leading and lead_elevated:
                    subtype = rng.choices(["failure", "inspection", "maintenance"], weights=[0.6, 0.2, 0.2])[0]
                else:
                    subtype = rng.choice(["failure", "inspection", "maintenance"])
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="EQUIPMENT",
                        event_subtype=subtype,
                        event_time=t, ingestion_time=t,
                        status=rng.choice(["OPEN", "OVERDUE", "CLOSED"]),
                    )
                )
            if rng.random() < 0.1:
                if training_deterioration:
                    overdue_share = 0.15 + 0.55 * (day / max(num_days - 1, 1))
                    status = rng.choices(
                        ["COMPLETED", "OVERDUE", "EXPIRED"],
                        weights=[max(0.05, 1 - overdue_share), overdue_share * 0.6, overdue_share * 0.4],
                    )[0]
                else:
                    status = rng.choice(["COMPLETED", "OVERDUE", "EXPIRED"])
                db.add(
                    make_safety_event(
                        organization_id=org.id, site_id=site.id, event_type="TRAINING",
                        event_time=t, ingestion_time=t,
                        status=status,
                    )
                )

            # The target itself: INCIDENT probability follows the
            # regime -- this is what a working pipeline should be able to
            # (weakly) pick up on via the leading-indicator features.
            if rng.random() < risk_fn(day, num_days):
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


def _reporting_dropoff(day: int, num_days: int) -> float:
    """Reporting volume falls to 30% of normal in the final third of the
    window while the underlying incident risk stays flat (`_stable_risk_regime`)
    -- a reporting-culture change, not a real risk change (item 42's
    "reporting-bias scenario")."""
    return 0.3 if day > (2 * num_days / 3) else 1.0


def seed_stable_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """Flat incident risk for the whole window -- no regime change to
    detect (item 42's "stable period")."""
    return seed_synthetic_organization(
        db, name=name or f"Stable Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_stable_risk_regime, **kwargs,
    )


def seed_increasing_risk_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """Risk rises steadily across the whole window (item 42's
    "increasing-risk period")."""
    return seed_synthetic_organization(
        db, name=name or f"Increasing Risk Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_increasing_risk_regime, **kwargs,
    )


def seed_decreasing_risk_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """Risk falls steadily across the whole window (item 42's
    "decreasing-risk period")."""
    return seed_synthetic_organization(
        db, name=name or f"Decreasing Risk Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_decreasing_risk_regime, **kwargs,
    )


def seed_sparse_data_organization(
    db: Session,
    *,
    name: str | None = None,
    site_names: list[str] | None = None,
    seed: int = 1,
    num_days: int = 180,
    stride_days: int = 21,
    **kwargs,
) -> tuple[Organization, list[Site]]:
    """One site, a long reporting stride, and a short window -- deliberately
    little data (item 42's "sparse-data period"), the shape
    `app/predictions/data_requirements.py::check_minimum_requirements()`
    is meant to catch as `INSUFFICIENT_DATA` rather than silently
    training on."""
    return seed_synthetic_organization(
        db, name=name or f"Sparse Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Sparse Site"],
        seed=seed, num_days=num_days, stride_days=stride_days, **kwargs,
    )


def seed_stale_data_organization(
    db: Session,
    *,
    name: str | None = None,
    site_names: list[str] | None = None,
    seed: int = 1,
    num_days: int = DEFAULT_NUM_DAYS,
    stale_gap_days: int = 200,
    **kwargs,
) -> tuple[Organization, list[Site]]:
    """Events stop `stale_gap_days` before the declared window ends --
    the ingestion-pipeline-went-quiet shape (item 42's "stale-data
    period"); pass `as_of=start + timedelta(days=num_days)` to
    `validate_dataset()`/`register_dataset()` to see the resulting
    `FreshnessReport` flag it."""
    return seed_synthetic_organization(
        db, name=name or f"Stale Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, num_days=num_days, stop_after_days=max(num_days - stale_gap_days, 1), **kwargs,
    )


def seed_reporting_bias_organization(
    db: Session,
    *,
    name: str | None = None,
    site_names: list[str] | None = None,
    seed: int = 1,
    reporting_multiplier_fn=None,
    **kwargs,
) -> tuple[Organization, list[Site]]:
    """Reporting volume (NEAR_MISS/OBSERVATION) drops in the back third
    of the window while actual incident risk stays flat (item 42's
    "reporting-bias scenario") -- a model or governance check that reads
    "fewer near-misses reported" as "risk went down" is exactly the
    mistake this scenario exists to catch."""
    return seed_synthetic_organization(
        db, name=name or f"Reporting Bias Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_stable_risk_regime, reporting_multiplier_fn=reporting_multiplier_fn or _reporting_dropoff,
        **kwargs,
    )


def seed_equipment_failure_leading_indicator_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """EQUIPMENT failure reports cluster ahead of the regime-change
    window's elevated-risk period (item 42's "equipment-failure
    scenario") -- a genuine leading indicator, not a coincident one."""
    return seed_synthetic_organization(
        db, name=name or f"Equipment Leading Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, equipment_leading=True, **kwargs,
    )


def seed_corrective_action_deterioration_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """Corrective actions increasingly go OPEN/OVERDUE rather than
    CLOSED as risk rises (item 42's "corrective-action deterioration
    scenario")."""
    return seed_synthetic_organization(
        db, name=name or f"Corrective Action Deterioration Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_increasing_risk_regime, corrective_action_deterioration=True, **kwargs,
    )


def seed_training_deterioration_organization(
    db: Session, *, name: str | None = None, site_names: list[str] | None = None, seed: int = 1, **kwargs
) -> tuple[Organization, list[Site]]:
    """Training compliance increasingly goes OVERDUE/EXPIRED rather than
    COMPLETED as risk rises (item 42's "training deterioration
    scenario")."""
    return seed_synthetic_organization(
        db, name=name or f"Training Deterioration Org {uuid.uuid4().hex[:8]}", site_names=site_names or ["Site 1"],
        seed=seed, risk_fn=_increasing_risk_regime, training_deterioration=True, **kwargs,
    )


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
