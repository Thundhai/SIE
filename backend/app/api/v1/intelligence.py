"""Intelligence & Predictive Analytics API — milestone items 9, 27, 37;
extended by Intelligence Platform Integration & Enterprise API v0.1,
items 17, 30, 38.

    external system -> Authorization: Bearer <client_id>:<secret>
        -> require_scope(SAFETY_DATA_WRITE)
        -> POST .../events | .../events/batch
        -> GenericJSONAdapter -> SafetyEventIngestionService -> SafetyEvent rows

    human OR machine caller -> RequestContext -> authorize_context(INTELLIGENCE_READ, organization_id)
        -> GET .../analytics/summary | .../analytics/trends | .../analytics/signals | .../features

**External applications never touch the database directly** (milestone
item 37) — every write goes through validation/normalization/idempotent
upsert (`app/intelligence/ingestion_service.py`); every read goes through
`app/intelligence/analytics.py`'s composition layer.

**Tenant isolation (milestone item 36).** Ingestion trusts only the
authenticated `MachineClientContext.organization_id` — never a client-
supplied `organization_id` field in the payload (there is no such field
on `SafetyEventCreate` at all). Reads require `organization_id` as an
explicit, authorized query parameter, the same
authenticate-then-authorize-then-pass-a-trusted-value shape
`app/api/v1/retrieval.py`/`app/api/v1/rag.py` already establish.

**Analytics reads now accept a machine caller too** (item 17's
`intelligence:analytics` scope example, item 30's third-party
integration example — "POST safety events -> SIE -> Analytics -> Risk
signals -> External HSE Platform" only makes sense end to end if the
same external system can read analytics back, not only push events).
`app.api.deps_context.RequestContext`/`require_context_permission()` is
the one dependency that accepts either identity kind — reusing
`Permission.INTELLIGENCE_READ` as the machine scope too (see that
module's own docstring for why this codebase does not maintain a second,
parallel scope vocabulary).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.api.deps_machine_auth import MachineClientContext, require_scope
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.config import settings
from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.analytics import compute_summary, compute_trend
from app.intelligence.attention import AttentionResult, compose_attention
from app.intelligence.context_composition import (
    FieldIntelligenceContextResult,
    compose_field_intelligence_context,
)
from app.intelligence.enterprise_intelligence_service import (
    EnterpriseIntelligenceResult,
    compute_enterprise_intelligence,
)
from app.intelligence.features import feature_engineering_service
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.intelligence.memory_integration import MemoryIntegrationContext, resolve_eligible_organizational_memories
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.signals import risk_signal_service
from app.intelligence.temporal import is_project_site_associated_as_of, project_site_ids_as_of
from app.models.project import Project
from app.models.site import Site
from app.schemas.attention import (
    AttentionCategoryStatusRead,
    AttentionEvidenceRead,
    AttentionItemRead,
    AttentionResultRead,
)
from app.schemas.enterprise_intelligence import (
    ActionsContextRead,
    ConcentrationContributorRead,
    DataSufficiencyRead,
    EnterpriseAnomalyRead,
    EnterpriseAssociationRead,
    EnterpriseIndicatorRead,
    EnterpriseIntelligenceRead,
    EnterpriseTrendRead,
    ExplanationItemRead,
    PredictiveContextRead,
    ProvenanceRead,
    RecurrencePatternRead,
    RiskScoreComponentRead,
    RiskScoreRead,
)
from app.schemas.field_intelligence_context import (
    FieldIntelligenceContextRead,
    KnowledgeEvidenceRead,
    ObservedActionRead,
    ObservedFactRead,
    ObservedFindingRead,
    OperationalScopeProjectRead,
    OperationalScopeRead,
    OperationalScopeSiteRead,
    OrganizationalMemoryContextRead,
    PredictiveSignalRead,
)
from app.schemas.intelligence import (
    AnalyticsSummaryRead,
    BatchIngestionRead,
    FeaturesRead,
    FeatureValueRead,
    IndicatorValueRead,
    IngestionIssueRead,
    IngestionRecordRead,
    RiskSignalRead,
    SafetyEventBatchCreate,
    SafetyEventCreate,
    SourceReliabilityRead,
    TrendPeriodRead,
    TrendResultRead,
)
from app.schemas.memory_integration import IntegratedMemoryRead, MemoryIntegrationContextRead
from app.schemas.retrieval import RetrievalResultRead
from app.services.permissions import Permission
from app.services.project_service import resolve_project_reference
from app.services.project_site_service import project_site_ids

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

_adapter = GenericJSONAdapter()


def _to_raw_payload(body: SafetyEventCreate) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type=body.event_type,
        event_subtype=body.event_subtype,
        event_time=body.event_time,
        period_end=body.period_end,
        reported_time=body.reported_time,
        site_id=body.site_id,
        location=body.location,
        project=body.project,
        department=body.department,
        contractor=body.contractor,
        activity=body.activity,
        severity=body.severity,
        potential_severity=body.potential_severity,
        status=body.status,
        description=body.description,
        attributes=body.attributes,
        source_system=body.source_system,
        source_record_id=body.source_record_id,
        source_record_version=body.source_record_version,
        correlation_id=body.correlation_id,
        source_schema_version=body.source_schema_version,
    )


def _to_record_read(result) -> IngestionRecordRead:
    return IngestionRecordRead(
        outcome=result.outcome.value,
        event_id=result.event_id,
        data_quality_status=result.data_quality_status,
        issues=[IngestionIssueRead(**issue) for issue in result.issues],
        duplicate_in_batch=result.duplicate_in_batch,
        source_system=result.source_system,
        source_record_id=result.source_record_id,
    )


# --- Ingestion (machine-client authenticated) ---------------------------------------


@router.post(
    "/events", response_model=IngestionRecordRead, dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))]
)
def ingest_event(
    body: SafetyEventCreate,
    context: MachineClientContext = Depends(require_scope(Permission.SAFETY_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> IngestionRecordRead:
    result = safety_event_ingestion_service.ingest_event(
        db,
        organization_id=context.organization_id,
        payload=_to_raw_payload(body),
        adapter=_adapter,
    )
    return _to_record_read(result)


@router.post(
    "/events/batch",
    response_model=BatchIngestionRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def ingest_event_batch(
    body: SafetyEventBatchCreate,
    context: MachineClientContext = Depends(require_scope(Permission.SAFETY_DATA_WRITE)),
    db: Session = Depends(get_db),
) -> BatchIngestionRead:
    batch_result = safety_event_ingestion_service.ingest_batch(
        db,
        organization_id=context.organization_id,
        payloads=[_to_raw_payload(event) for event in body.events],
        adapter=_adapter,
    )
    return BatchIngestionRead(
        batch_id=batch_result.batch_id,
        record_count=len(batch_result.records),
        created_count=batch_result.created_count,
        updated_count=batch_result.updated_count,
        skipped_idempotent_count=batch_result.skipped_idempotent_count,
        rejected_count=batch_result.rejected_count,
        duplicate_in_batch_count=batch_result.duplicate_in_batch_count,
        records=[_to_record_read(r) for r in batch_result.records],
    )


# --- Analytics (human OR machine, tenant-authorized) ------------------------------


@router.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def analytics_summary(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryRead:
    entity_type = "site" if site_id is not None else "organization"
    summary = compute_summary(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days, entity_type=entity_type
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="summary")
    return AnalyticsSummaryRead(
        organization_id=summary.organization_id,
        entity_type=summary.entity_type,
        entity_id=summary.entity_id,
        as_of=summary.as_of,
        window_days=summary.window_days,
        event_count=summary.event_count,
        data_sufficiency=summary.data_sufficiency,
        features={name: _feature_read(f) for name, f in summary.features.items()},
        indicators=[
            IndicatorValueRead(name=i.name, category=i.category, feature=_feature_read(i.feature))
            for i in summary.indicators
        ],
        signals=[_signal_read(s) for s in summary.signals],
        source_reliability=[SourceReliabilityRead(**vars(r)) for r in summary.source_reliability],
    )


@router.get(
    "/analytics/trends",
    response_model=TrendResultRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def analytics_trends(
    organization_id: uuid.UUID = Query(...),
    metric: str = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    period_days: int | None = Query(default=None, ge=1, le=3650),
    num_periods: int | None = Query(default=None, ge=2, le=52),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> TrendResultRead:
    try:
        trend = compute_trend(
            db,
            organization_id=organization_id,
            metric=metric,
            site_id=site_id,
            period_days=period_days,
            num_periods=num_periods,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="trends")
    return TrendResultRead(
        metric=trend.metric,
        direction=trend.direction,
        periods=[TrendPeriodRead(period_start=p.period_start, period_end=p.period_end, value=p.value) for p in trend.periods],
        slope=trend.slope,
        relative_slope=trend.relative_slope,
        calculation_version=trend.calculation_version,
        method=trend.method,
    )


@router.get(
    "/analytics/signals",
    response_model=list[RiskSignalRead],
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def analytics_signals(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> list[RiskSignalRead]:
    signals = risk_signal_service.detect_all(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="signals")
    return [_signal_read(s) for s in signals]


@router.get(
    "/features",
    response_model=FeaturesRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def features(
    organization_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    window_days: int | None = Query(default=None, ge=1, le=3650),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> FeaturesRead:
    entity_type = "site" if site_id is not None else "organization"
    feature_values = feature_engineering_service.compute(
        db, organization_id=organization_id, site_id=site_id, window_days=window_days, entity_type=entity_type
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="features")
    return FeaturesRead(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=site_id,
        as_of=next(iter(feature_values.values())).as_of,
        window_days=next(iter(feature_values.values())).window_days,
        features={name: _feature_read(f) for name, f in feature_values.items()},
    )


def _feature_read(f) -> FeatureValueRead:
    return FeatureValueRead(
        name=f.name,
        value=f.value,
        window_days=f.window_days,
        as_of=f.as_of,
        entity_type=f.entity_type,
        entity_id=f.entity_id,
        source_event_ids=f.source_event_ids,
        calculation_version=f.calculation_version,
        data_quality=f.data_quality,
        exposure_basis=f.exposure_basis,
        unavailable_reason=f.unavailable_reason,
    )


def _signal_read(s) -> RiskSignalRead:
    return RiskSignalRead(
        signal_type=s.signal_type,
        severity=s.severity,
        observed_period_start=s.observed_period_start,
        observed_period_end=s.observed_period_end,
        entity_type=s.entity_type,
        entity_id=s.entity_id,
        supporting_features=s.supporting_features,
        supporting_event_ids=s.supporting_event_ids,
        data_quality=s.data_quality,
        calculation_version=s.calculation_version,
    )


# --- Enterprise intelligence (SIE Milestone 22, human OR machine, tenant-authorized) ---


def _require_owned_site(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    """Entity-ownership check, mirroring `app/api/v1/predictions.py`'s own
    `_require_owned_site()` exactly — a 404, not a 403, for a site that
    either doesn't exist or belongs to a different organization: this
    endpoint never reveals whether a given id exists in someone else's
    tenant (milestone item 15)."""
    site = db.execute(
        select(Site).where(Site.id == site_id, Site.organization_id == organization_id)
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found in this organization.")
    return site


def _validate_window_days(window_days: int) -> None:
    if window_days not in settings.ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"window_days must be one of {settings.ENTERPRISE_INTELLIGENCE_ALLOWED_WINDOW_DAYS}, "
                f"got {window_days}."
            ),
        )


def _to_enterprise_intelligence_read(result: EnterpriseIntelligenceResult) -> EnterpriseIntelligenceRead:
    return EnterpriseIntelligenceRead(
        scope=result.scope,
        organization_id=result.organization_id,
        entity_id=result.entity_id,
        as_of=result.as_of,
        window_days=result.window_days,
        data_sufficiency=DataSufficiencyRead(status=result.data_sufficiency, event_count=result.event_count),
        deterministic_risk=RiskScoreRead(
            score=result.risk.score,
            classification=result.risk.classification,
            version=result.risk.version,
            components=[RiskScoreComponentRead(**vars(c)) for c in result.risk.components],
            insufficient_data_reason=result.risk.insufficient_data_reason,
        ),
        trend=EnterpriseTrendRead(**vars(result.trend)),
        indicators=[EnterpriseIndicatorRead(**vars(i)) for i in result.indicators],
        patterns=[RecurrencePatternRead(**vars(p)) for p in result.patterns],
        concentrations=[ConcentrationContributorRead(**vars(c)) for c in result.concentrations],
        anomalies=[EnterpriseAnomalyRead(**vars(a)) for a in result.anomalies],
        associations=[EnterpriseAssociationRead(**vars(a)) for a in result.associations],
        explanations=[ExplanationItemRead(**vars(e)) for e in result.explanations],
        provenance=ProvenanceRead(**vars(result.provenance)),
        predictive_context=(
            PredictiveContextRead(**vars(result.predictive_context)) if result.predictive_context else None
        ),
        actions_context=(ActionsContextRead(**vars(result.actions_context)) if result.actions_context else None),
    )


@router.get(
    "/enterprise",
    response_model=EnterpriseIntelligenceRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def enterprise_intelligence(
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> EnterpriseIntelligenceRead:
    """Organization-scope enterprise intelligence (milestone item 14).
    `organization_id` is the same authorize-then-trust query parameter
    every other endpoint in this router already uses — never overridable
    beyond what `require_context_permission()` itself authorized (a
    machine caller's own pinned `organization_id`, or a human caller's
    own authorized membership — see `app/api/deps_context.py`)."""
    _validate_window_days(window_days)
    result = compute_enterprise_intelligence(
        db, organization_id=organization_id, scope="organization", as_of=as_of, window_days=window_days
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="enterprise")
    return _to_enterprise_intelligence_read(result)


@router.get(
    "/sites/{site_id}",
    response_model=EnterpriseIntelligenceRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def site_intelligence(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> EnterpriseIntelligenceRead:
    """Site-scope enterprise intelligence (milestone item 14). The site
    must belong to `organization_id` — a site from a different
    organization (or a nonexistent id) is a 404, never a 403 (milestone
    item 15's own "consistent with existing APIs" instruction, mirroring
    `app/api/v1/predictions.py`)."""
    _validate_window_days(window_days)
    _require_owned_site(db, organization_id=organization_id, site_id=site_id)
    result = compute_enterprise_intelligence(
        db, organization_id=organization_id, scope="site", site_id=site_id, as_of=as_of, window_days=window_days
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="sites")
    return _to_enterprise_intelligence_read(result)


# --- Field Intelligence Context (SIE Milestone 32, human OR machine, tenant-authorized) ---


def _to_retrieval_result_read(r) -> RetrievalResultRead:
    """Identical field mapping to `app/api/v1/retrieval.py::search_knowledge()`'s
    own inline construction — not a second retrieval implementation,
    just the same one-time dataclass -> schema conversion every route
    that returns a `RetrievalResult` performs for its own response
    model."""
    return RetrievalResultRead(
        rank=r.rank,
        chunk_id=r.chunk_id,
        similarity=r.similarity,
        relevance=r.relevance.value,
        content=r.content,
        content_type=r.content_type,
        source_id=r.source_id,
        document_id=r.document_id,
        document_version_id=r.document_version_id,
        source=r.source_name,
        document=r.document_title,
        version=r.version_label,
        location=r.location,
        page_number=r.page_number,
        sheet_name=r.sheet_name,
        row_number=r.row_number,
        slide_number=r.slide_number,
        section_title=r.section_title,
        section_path=r.section_path,
        extraction_quality=r.extraction_quality,
        extraction_method=r.extraction_method,
        source_authority_level=r.source_authority_level,
        verification_status=r.verification_status,
        scope=r.scope,
        organization_id=r.organization_id,
        jurisdiction=r.jurisdiction,
        industry_sector=r.industry_sector,
        publication_date=r.publication_date,
        effective_date=r.effective_date,
    )


def _build_operational_scope(
    db: Session,
    *,
    organization_id: uuid.UUID,
    level: str,
    site: Site | None,
    project_id: uuid.UUID | None,
    as_of: datetime | None,
) -> OperationalScopeRead | None:
    """SIE Milestone 35: builds the additive `operational_scope` label
    for a Field Intelligence Context response. Returns `None` when
    `project_id` was never supplied -- every pre-M35 caller's response
    is therefore byte-for-byte unchanged. `level` is always the *actual*
    `scope` this request computed over (`"ORGANIZATION"`/`"SITE"`) --
    this function never computes anything itself, only labels what was
    already computed (see this module's own schema docstring for the
    full "label, never a second computation engine" rationale).

    **`site_ids`/the site-consistency check are point-in-time correct
    when the caller explicitly supplies `as_of` (SIE Milestone 36) --
    current-state (the fast `project_sites` table, via
    `project_site_ids()`) otherwise.** `as_of` here is the router's own
    *raw* query parameter -- still `None` when the caller omitted it,
    not yet defaulted to `utcnow()` the way
    `compose_field_intelligence_context()` defaults it internally. This
    is the deliberate CURRENT-vs-HISTORICAL split item 5 of this
    milestone requires: the overwhelmingly common live case (`as_of`
    omitted) never pays for a `ProjectSiteHistory` reconstruction query
    it doesn't need; a caller who explicitly asks about a historical
    instant gets a response whose `site_ids` and site-consistency
    validation both genuinely reflect that instant, reconstructed from
    `app/intelligence/temporal.py::project_site_ids_as_of()`/
    `is_project_site_associated_as_of()` -- never today's `project_sites`
    row. See `docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md` §11 for the
    full account, including why this is the one intelligence path this
    milestone touches (every other path either has no semantic
    dependency on `ProjectSite` membership at all, or -- like
    `attribute_event_to_project()`'s own write-time site-consistency
    check -- is deliberately a *current*-state business rule, not a
    historical computation)."""
    if project_id is None:
        return None
    project = resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    if as_of is None:
        site_ids = project_site_ids(db, organization_id=organization_id, project_id=project.id)
        currently_associated = site is None or site.id in site_ids
    else:
        site_ids = project_site_ids_as_of(db, organization_id=organization_id, project_id=project.id, as_of=as_of)
        currently_associated = site is None or is_project_site_associated_as_of(
            db, organization_id=organization_id, project_id=project.id, site_id=site.id, as_of=as_of
        )
    if site is not None and not currently_associated:
        detail = (
            f"Site {site.id} is not associated with project {project.id} as of {as_of.isoformat()}."
            if as_of is not None
            else f"Site {site.id} is not currently associated with project {project.id}."
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return OperationalScopeRead(
        level=level,
        site=(OperationalScopeSiteRead(id=site.id, name=site.name) if site is not None else None),
        project=OperationalScopeProjectRead(
            id=project.id, name=project.name, code=project.code, status=project.status.value, site_ids=site_ids
        ),
    )


def _to_field_intelligence_context_read(
    result: FieldIntelligenceContextResult, *, operational_scope: OperationalScopeRead | None = None
) -> FieldIntelligenceContextRead:
    observed = result.observed
    predictive = result.predictive
    knowledge = result.knowledge
    knowledge_response = knowledge.response
    return FieldIntelligenceContextRead(
        scope=result.scope,
        organization_id=result.organization_id,
        entity_id=result.entity_id,
        as_of=result.as_of,
        window_days=result.window_days,
        generated_at=result.generated_at,
        observed=ObservedFactRead(
            outcome=observed.outcome,
            unavailable_reason=observed.unavailable_reason,
            event_count=observed.event_count,
            evidence_sample_event_ids=observed.evidence_sample_event_ids,
            open_finding_count=observed.open_finding_count,
            open_finding_sample=[
                ObservedFindingRead(**vars(f)) for f in observed.open_finding_sample
            ],
            open_finding_control_count=observed.open_finding_control_count,
            actions=(ActionsContextRead(**vars(observed.actions)) if observed.actions else None),
            open_action_sample=[ObservedActionRead(**vars(a)) for a in observed.open_action_sample],
        ),
        deterministic=_to_enterprise_intelligence_read(result.deterministic),
        predictive=PredictiveSignalRead(
            outcome=predictive.outcome,
            value=(PredictiveContextRead(**vars(predictive.value)) if predictive.value else None),
        ),
        knowledge=KnowledgeEvidenceRead(
            outcome=knowledge.outcome,
            unavailable_reason=knowledge.unavailable_reason,
            query=knowledge_response.query if knowledge_response else None,
            results=(
                [_to_retrieval_result_read(r) for r in knowledge_response.results] if knowledge_response else []
            ),
            result_count=(knowledge_response.result_count if knowledge_response else 0),
        ),
        organizational_memory=OrganizationalMemoryContextRead(
            outcome=result.organizational_memory.outcome,
            unavailable_reason=result.organizational_memory.unavailable_reason,
            items=[IntegratedMemoryRead(**vars(item)) for item in result.organizational_memory.items],
            calculation_version=result.organizational_memory.calculation_version,
        ),
        calculation_versions=result.calculation_versions,
        operational_scope=operational_scope,
    )


@router.get(
    "/context",
    response_model=FieldIntelligenceContextRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def field_intelligence_context(
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    knowledge_query: str | None = Query(default=None, min_length=1, max_length=2000),
    knowledge_top_k: int | None = Query(default=None, ge=1, le=settings.RETRIEVAL_MAX_TOP_K),
    project_id: uuid.UUID | None = Query(
        default=None,
        description="SIE Milestone 35A: when supplied, genuinely filters observed.event_count/"
        "evidence_sample_event_ids and deterministic.indicators/trend/concentrations/patterns/risk to "
        "SafetyEvent rows explicitly attributed to this project (never site co-location). "
        "deterministic.anomalies/associations, predictive, observed.actions, and observed.open_finding_sample "
        "remain Organization/Site scope -- see the response's own operational_scope.project.filtered field.",
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> FieldIntelligenceContextRead:
    """Organization-scope Field Intelligence Context (SIE Milestone 32).
    Composes the four categories defined by
    `backend/docs/SIE_FIELD_INTELLIGENCE_CONTEXT_V0_1.md` §7 — Observed,
    Deterministic, Predictive, Knowledge/Evidence — never merging them.
    `organization_id` is the same authorize-then-trust query parameter
    every other endpoint in this router already uses. `knowledge_query`
    is optional: when omitted, the Knowledge/Evidence category reports
    `NOT_QUERIED` rather than fabricating a search from other fields."""
    _validate_window_days(window_days)
    operational_scope = _build_operational_scope(
        db, organization_id=organization_id, level="ORGANIZATION", site=None, project_id=project_id, as_of=as_of
    )
    result = compose_field_intelligence_context(
        db,
        organization_id=organization_id,
        scope="organization",
        project_id=project_id,
        as_of=as_of,
        window_days=window_days,
        knowledge_query=knowledge_query,
        knowledge_top_k=knowledge_top_k,
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="context")
    return _to_field_intelligence_context_read(result, operational_scope=operational_scope)


@router.get(
    "/sites/{site_id}/context",
    response_model=FieldIntelligenceContextRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def site_field_intelligence_context(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    knowledge_query: str | None = Query(default=None, min_length=1, max_length=2000),
    knowledge_top_k: int | None = Query(default=None, ge=1, le=settings.RETRIEVAL_MAX_TOP_K),
    project_id: uuid.UUID | None = Query(
        default=None,
        description="SIE Milestone 35A: must be associated with `site_id` (400 otherwise) -- as of `as_of` when "
        "explicitly supplied (SIE Milestone 36), else currently. See GET /intelligence/context's own description "
        "for exactly what this genuinely filters.",
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> FieldIntelligenceContextRead:
    """Site-scope Field Intelligence Context (SIE Milestone 32). The
    site must belong to `organization_id` — a site from a different
    organization (or a nonexistent id) is a 404, never a 403, mirroring
    `site_intelligence()` above exactly."""
    _validate_window_days(window_days)
    site = _require_owned_site(db, organization_id=organization_id, site_id=site_id)
    operational_scope = _build_operational_scope(
        db, organization_id=organization_id, level="SITE", site=site, project_id=project_id, as_of=as_of
    )
    result = compose_field_intelligence_context(
        db,
        organization_id=organization_id,
        scope="site",
        site_id=site_id,
        project_id=project_id,
        as_of=as_of,
        window_days=window_days,
        knowledge_query=knowledge_query,
        knowledge_top_k=knowledge_top_k,
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="sites_context")
    return _to_field_intelligence_context_read(result, operational_scope=operational_scope)


# --- Learning Integration (SIE Milestone 41, human OR machine, tenant-authorized) --------------
#
# A fifth, independent category alongside M32's own Observed/
# Deterministic/Predictive/Knowledge -- never merged into any of them,
# exposed as its own endpoints rather than a new field on
# `FieldIntelligenceContextRead` so this milestone's read-only
# composition (`app/intelligence/memory_integration.py`) stays fully
# decoupled from M32's own, separately-tested response contract. See
# that module's own docstring for the full "why no persisted
# integration table" and applicability/temporal rationale.


def _to_memory_integration_context_read(
    result: MemoryIntegrationContext, *, page: int, page_size: int
) -> MemoryIntegrationContextRead:
    total = len(result.items)
    page_items = result.items[(page - 1) * page_size : (page - 1) * page_size + page_size]
    return MemoryIntegrationContextRead(
        scope=result.scope,
        organization_id=result.organization_id,
        entity_id=result.entity_id,
        project_id=result.project_id,
        as_of=result.as_of,
        generated_at=result.generated_at,
        items=[IntegratedMemoryRead(**vars(item)) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
        calculation_version=result.calculation_version,
    )


@router.get(
    "/memory-context",
    response_model=MemoryIntegrationContextRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def organization_memory_context(
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff. A memory created after as_of is never included, and "
        "governance is resolved as of this same instant -- see docs/LEARNING_INTEGRATION_V0_1.md."
    ),
    project_id: uuid.UUID | None = Query(
        default=None,
        description="Narrows applicability to memories whose originating outcome's site is associated with this "
        "project as of as_of, plus organization-wide memories. Omit for the full organization-scope rollup.",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> MemoryIntegrationContextRead:
    """Organization-scope: which currently-ACTIVE (or ACTIVE as of
    `as_of`) organizational memories are applicable to this
    organization's intelligence context right now (SIE Milestone 41).
    Read-only, deterministic -- never trains, retrains, or mutates any
    model, threshold, rule, ontology, or terminology."""
    result = resolve_eligible_organizational_memories(
        db, organization_id=organization_id, scope="organization", project_id=project_id, as_of=as_of
    )
    return _to_memory_integration_context_read(result, page=page, page_size=page_size)


@router.get(
    "/sites/{site_id}/memory-context",
    response_model=MemoryIntegrationContextRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def site_memory_context(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> MemoryIntegrationContextRead:
    """Site-scope: organization-wide memories plus memories whose own
    originating outcome belongs to this exact site. The site must
    belong to `organization_id` — a site from a different organization
    (or a nonexistent id) is a 404, never a 403, mirroring
    `site_field_intelligence_context()` exactly. `project_id` is not
    accepted here: a site scope is already a single, fixed site, so a
    project filter would add no further narrowing (mirrors
    `compute_enterprise_intelligence()`'s own identical site-scope
    behavior)."""
    _require_owned_site(db, organization_id=organization_id, site_id=site_id)
    result = resolve_eligible_organizational_memories(
        db, organization_id=organization_id, scope="site", site_id=site_id, as_of=as_of
    )
    return _to_memory_integration_context_read(result, page=page, page_size=page_size)


# --- Attention & Delivery (SIE Milestone 33, human OR machine, tenant-authorized) ---


def _to_attention_read(result: AttentionResult) -> AttentionResultRead:
    return AttentionResultRead(
        scope=result.scope,
        organization_id=result.organization_id,
        entity_id=result.entity_id,
        as_of=result.as_of,
        window_days=result.window_days,
        generated_at=result.generated_at,
        items=[
            AttentionItemRead(
                category=item.category,
                priority=item.priority,
                title=item.title,
                explanation=item.explanation,
                scope=item.scope,
                site_id=item.site_id,
                site_label=item.site_label,
                as_of=item.as_of,
                window_days=item.window_days,
                evidence=AttentionEvidenceRead(**vars(item.evidence)),
                limitation=item.limitation,
                reference=item.reference,
            )
            for item in result.items
        ],
        category_statuses=[AttentionCategoryStatusRead(**vars(s)) for s in result.category_statuses],
        calculation_versions=result.calculation_versions,
    )


@router.get(
    "/attention",
    response_model=AttentionResultRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def organization_attention(
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> AttentionResultRead:
    """Organization-scope attention (SIE Milestone 33): "what should a
    human pay attention to right now, and why?" -- built entirely on top
    of the existing Field Intelligence Context (M32) and enterprise
    intelligence orchestration (M22-24); see `app/intelligence/attention.py`
    for the full category/prioritization contract. Read-only: this
    endpoint creates nothing (no action, no finding, no intervention) --
    it only surfaces and explains what already-existing intelligence
    already computed. Permission-gated identically to
    `/intelligence/enterprise` and `/intelligence/context` above (same
    `INTELLIGENCE_READ` permission, same authorize-then-trust
    `organization_id`)."""
    _validate_window_days(window_days)
    result = compose_attention(db, organization_id=organization_id, scope="organization", as_of=as_of, window_days=window_days)
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="attention")
    return _to_attention_read(result)


@router.get(
    "/sites/{site_id}/attention",
    response_model=AttentionResultRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def site_attention(
    site_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(default=None),
    window_days: int = Query(default=settings.ENTERPRISE_INTELLIGENCE_DEFAULT_WINDOW_DAYS),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> AttentionResultRead:
    """Site-scope attention (SIE Milestone 33). The site must belong to
    `organization_id` -- a site from a different organization (or a
    nonexistent id) is a 404, never a 403, mirroring
    `site_field_intelligence_context()` above exactly."""
    _validate_window_days(window_days)
    _require_owned_site(db, organization_id=organization_id, site_id=site_id)
    result = compose_attention(
        db, organization_id=organization_id, scope="site", site_id=site_id, as_of=as_of, window_days=window_days
    )
    _audit_analytics_query(db, context=context, organization_id=organization_id, endpoint="sites_attention")
    return _to_attention_read(result)


def _audit_analytics_query(db: Session, *, context: RequestContext, organization_id: uuid.UUID, endpoint: str) -> None:
    from app.services.audit_service import AuditAction, audit_service

    audit_service.log(
        db,
        action=AuditAction.INTELLIGENCE_ANALYTICS_QUERIED,
        resource_type="IntelligenceAnalytics",
        organization_id=organization_id,
        user_id=context.user_id,  # None for a machine caller -- its own API_AUTHENTICATED row already names the client
        metadata={"endpoint": endpoint, "caller_kind": context.kind},
    )
