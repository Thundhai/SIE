"""Intelligence & Predictive Analytics evaluation harness — milestone
items 40-41. "Prototype evaluation" per the identical honesty standard
`tests/evaluation/harness.py` (Recall@K) and `tests/evaluation/rag_harness.py`
already establish: a small, synthetic, regression-catching check, never a
production/enterprise claim.

    seed_and_evaluate() -> real ingestion through SafetyEventIngestionService
        (six organization profiles — see tests/fixtures/intelligence/synthetic_dataset.py)
        -> real trend/signal/sufficiency/freshness/exposure computation
        -> IntelligenceEvaluationReport, every field a genuinely measured result

Nothing here is fabricated or extrapolated — every number comes from
actually running the production ingestion/analytics code path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.analytics import compute_summary, compute_trend
from app.intelligence.features import feature_engineering_service
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.intelligence.reliability import compute_source_reliability
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.signals import risk_signal_service
from app.intelligence.temporal import events_as_of, utcnow
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from tests.fixtures.intelligence.synthetic_dataset import ALL_PROFILES

LABEL = "Prototype intelligence evaluation result on synthetic fixture dataset — not a production benchmark."

_adapter = GenericJSONAdapter()


@dataclass
class IntelligenceEvaluationReport:
    label: str = LABEL
    organizations: dict[str, uuid.UUID] = field(default_factory=dict)
    ingestion_results: dict[str, dict] = field(default_factory=dict)
    trend_direction: str | None = None
    trending_org_signal_types: set[str] = field(default_factory=set)
    sparse_org_signal_count: int = 0
    sufficiency_by_org: dict[str, str] = field(default_factory=dict)
    stale_org_is_stale: bool | None = None
    fresh_org_is_stale: bool | None = None
    missing_exposure_unavailable_reason: str | None = None
    trending_org_exposure_rate: float | None = None
    temporal_leakage_detected: bool = False
    cross_tenant_leakage_count: int = 0

    def summary(self) -> str:
        return (
            f"{self.label} trend_direction={self.trend_direction}, "
            f"trending_org_signals={sorted(self.trending_org_signal_types)}, "
            f"sparse_org_signal_count={self.sparse_org_signal_count}, "
            f"sufficiency={self.sufficiency_by_org}, "
            f"stale_org_is_stale={self.stale_org_is_stale}, "
            f"fresh_org_is_stale={self.fresh_org_is_stale}, "
            f"missing_exposure_reason={self.missing_exposure_unavailable_reason}, "
            f"trending_org_exposure_rate={self.trending_org_exposure_rate}, "
            f"temporal_leakage_detected={self.temporal_leakage_detected}, "
            f"cross_tenant_leakage_count={self.cross_tenant_leakage_count}"
        )


def seed_and_evaluate(db: Session, *, base_time: datetime | None = None) -> IntelligenceEvaluationReport:
    # `base_time` is what the synthetic dataset's relative day-offsets
    # (see synthetic_dataset.py) are computed against -- essentially
    # "now". `as_of`, used for every analysis call below, is captured
    # *after* ingestion completes, not before: ingestion legitimately
    # stamps `SafetyEvent.ingestion_time` at real wall-clock "now" (see
    # SafetyEventIngestionService._apply()), and app/intelligence/temporal.py's
    # `events_as_of()` correctly refuses to use any row whose
    # `ingestion_time` is after `as_of` (that is the anti-leakage
    # guarantee this milestone is built around) -- so `as_of` captured
    # *before* ingesting would make every just-ingested row invisible to
    # every analysis call below, by design, not by bug.
    base_time = base_time or utcnow()
    report = IntelligenceEvaluationReport()

    orgs: dict[str, uuid.UUID] = {}
    for name in ALL_PROFILES:
        org = Organization(name=f"Evaluation - {name}")
        db.add(org)
        db.commit()
        orgs[name] = org.id
    report.organizations = orgs

    for name, builder in ALL_PROFILES.items():
        payloads = builder(base_time)
        batch_result = safety_event_ingestion_service.ingest_batch(
            db, organization_id=orgs[name], payloads=payloads, adapter=_adapter
        )
        report.ingestion_results[name] = {
            "created": batch_result.created_count,
            "updated": batch_result.updated_count,
            "skipped_idempotent": batch_result.skipped_idempotent_count,
            "rejected": batch_result.rejected_count,
            "duplicate_in_batch": batch_result.duplicate_in_batch_count,
        }

    # stale_data_org's whole premise is a source that has not sent fresh
    # data recently -- that is a statement about *ingestion* recency, not
    # event age (see app/intelligence/reliability.py). Backdating
    # `ingestion_time` directly is the honest way to simulate that in a
    # test that must otherwise ingest everything "now"; SafetyEventIngestionService
    # itself never does this, and no ordinary caller has a reason to.
    stale_cutoff = base_time - timedelta(days=90)
    for event in db.execute(select(SafetyEvent).where(SafetyEvent.organization_id == orgs["stale_data_org"])).scalars():
        event.ingestion_time = stale_cutoff
    db.commit()

    as_of = utcnow()

    # --- Trend analysis: trending_org's incident_count should increase ---------------
    trend = compute_trend(
        db, organization_id=orgs["trending_org"], metric="incident_count", as_of=as_of, period_days=30, num_periods=3
    )
    report.trend_direction = trend.direction

    # --- Risk signals -----------------------------------------------------------------
    trending_signals = risk_signal_service.detect_all(db, organization_id=orgs["trending_org"], as_of=as_of)
    report.trending_org_signal_types = {s.signal_type for s in trending_signals}
    sparse_signals = risk_signal_service.detect_all(db, organization_id=orgs["sparse_data_org"], as_of=as_of)
    report.sparse_org_signal_count = len(sparse_signals)

    # --- Data sufficiency ---------------------------------------------------------------
    for name in ("trending_org", "sparse_data_org"):
        summary = compute_summary(db, organization_id=orgs[name], as_of=as_of, window_days=365)
        report.sufficiency_by_org[name] = summary.data_sufficiency

    # --- Data freshness -----------------------------------------------------------------
    stale_reliability = compute_source_reliability(db, organization_id=orgs["stale_data_org"], as_of=as_of)
    report.stale_org_is_stale = stale_reliability[0].is_stale if stale_reliability else None
    fresh_reliability = compute_source_reliability(db, organization_id=orgs["trending_org"], as_of=as_of)
    report.fresh_org_is_stale = fresh_reliability[0].is_stale if fresh_reliability else None

    # --- Exposure normalization -----------------------------------------------------------
    missing_exposure_features = feature_engineering_service.compute(
        db, organization_id=orgs["missing_exposure_org"], as_of=as_of, window_days=365
    )
    report.missing_exposure_unavailable_reason = missing_exposure_features["incidents_per_100000_hours"].unavailable_reason
    trending_features = feature_engineering_service.compute(
        db, organization_id=orgs["trending_org"], as_of=as_of
    )
    report.trending_org_exposure_rate = trending_features["incidents_per_100000_hours"].value

    # --- Temporal integrity: a future-dated event must never leak in --------------------
    # The milestone's own worked example: predicting as-of `as_of`, a
    # database that also contains an event dated well after `as_of` must
    # never let that event enter the feature calculation.
    # strict_point_in_time=False isolates this check to event_time
    # specifically (this new row's own ingestion_time is unavoidably
    # after `as_of` too, since it is written after `as_of` was captured
    # -- see the comment at the top of this function -- so the default
    # strict filter would exclude it for that reason as well; this
    # proves the event_time boundary itself, not just the ingestion_time
    # one already exercised above).
    future_time = as_of + timedelta(days=30)
    future_result = safety_event_ingestion_service.ingest_event(
        db,
        organization_id=orgs["trending_org"],
        payload=RawSafetyEventPayload(
            event_type="INCIDENT", event_time=future_time.isoformat(),
            source_system="safelytic", source_record_id="future-leakage-check",
        ),
        adapter=_adapter,
    )
    query = events_as_of(
        organization_id=orgs["trending_org"], as_of=as_of, window_start=None, strict_point_in_time=False
    )
    visible_ids = {e.id for e in db.execute(query).scalars().all()}
    report.temporal_leakage_detected = future_result.event_id in visible_ids

    # --- Cross-tenant leakage: sparse_data_org must never see trending_org's events ------
    sparse_summary = compute_summary(db, organization_id=orgs["sparse_data_org"], as_of=as_of, window_days=365)
    expected_sparse_count = len(ALL_PROFILES["sparse_data_org"](base_time))
    report.cross_tenant_leakage_count = max(0, sparse_summary.event_count - expected_sparse_count)

    return report
