"""Risk Assessment API — SIE Milestone 25: Enterprise Risk Assessment
Foundation v0.1; extended by SIE Milestone 26: Formal Enterprise Risk
Assessment Engine v0.2.

    Organization / Site
       |
    POST /api/v1/risk-assessments | GET .../risk-assessments | GET .../{id}
    | PATCH .../{id} | POST .../{id}/submit | POST .../{id}/approve
    | POST .../{id}/archive | GET .../{id}/findings | POST .../{id}/findings
    | PATCH .../{id}/findings/{finding_id}
       |
    RequestContext (app.api.deps_context — human OR machine, unchanged)
       |
    Authorization (RISK_ASSESSMENT_READ/WRITE/APPROVE — app.services.permissions)
       |
    Tenant-scoped query/write (organization_id always the authorized
       |                        request-context value, never trusted
       |                        from the body)
    RiskAssessment / RiskAssessmentFinding (app.models.risk_assessment, new)

**Core architectural rule (item 1) — a layer above `enterprise-risk-v1`,
never a replacement.** This module never imports or calls
`app/intelligence/risk_score.py` directly to derive a rating; the only
place `enterprise-risk-v1` appears here is inside the read-only
`intelligence_context` (via `compute_intelligence_context()`), clearly
labeled with its own `calculation_versions`, never mixed into
`inherent_risk_score`/`residual_risk_score`.

**Minimum API surface (item 22), plus one addition.** The milestone's
own minimum list is create/list/retrieve/update-draft/submit/approve/
GET findings/POST findings (8 routes). This module adds exactly one
more: `PATCH .../{id}/findings/{finding_id}` — without it, a
system-generated candidate finding (item 14's own "HUMAN REVIEW" step)
would have no API path to ever be reviewed, rated, or given controls,
which would make item 27's entire architectural point unreachable
through this API. Everything else stays exactly at the milestone's own
named minimum — no "create new version"/"supersede" endpoint (folded
into `POST /risk-assessments` via `supersedes_assessment_id`, see
`app/services/risk_assessment_service.py::open_new_version()`), no
dedicated controls sub-resource (folded into the finding PATCH, see
`app/schemas/risk_assessment.py::RiskAssessmentFindingUpdate`'s own
docstring).

**Tenant isolation.** Every query below filters on
`RiskAssessment.organization_id == organization_id` (or, for findings,
join through the parent assessment's own organization_id) before
anything else — `organization_id` is always the value
`require_context_permission`/`authorize_context` already authorized the
caller for. A valid id belonging to a different organization is
indistinguishable from a nonexistent one: always `404`, mirroring
`app/api/v1/actions.py`'s own "Tenant isolation" precedent exactly.

**Immutability after approval (items 4, 23).** `require_editable()`
(`app/services/risk_assessment_service.py`) gates every mutating route
below except `submit`/`approve`/`archive` themselves (which have their
own `require_transition()` check) — an `APPROVED`/`SUPERSEDED`/`ARCHIVED`
assessment rejects `PATCH .../{id}` and every finding mutation with a
`422`.

**SIE Milestone 26 additions.** `POST .../{id}/archive` — the one new
route (manual retirement, see `RiskAssessmentStatus.ARCHIVED`'s own
docstring); `Idempotency-Key` support on `POST /risk-assessments`
(mirrors `app/api/v1/actions.py::create_action()`'s own established
pattern exactly); and a `RiskAssessmentHistory` entry written alongside
every mutation, in the same transaction, via
`app/services/risk_assessment_service.py::record_history()` (item 9:
"Assessment + Finding + History + Audit + Idempotency... a single
transaction boundary" -- "the lesson from Milestone 17").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.api.deps_context import RequestContext, authorize_context, require_context_permission
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.config import settings
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.risk_assessment import (
    RiskAssessment,
    RiskAssessmentControl,
    RiskAssessmentFinding,
    RiskAssessmentFindingEvidence,
)
from app.models.risk_assessment_enums import (
    FindingSource,
    FindingStatus,
    RiskAssessmentScope,
    RiskAssessmentStatus,
    RiskCandidateStatus,
    RiskEvidenceType,
)
from app.models.risk_assessment_finding_action import RiskAssessmentFindingAction
from app.models.safety_action import SafetyAction
from app.models.safety_action_enums import ActionStatus
from app.risk_assessment.candidate_generation import generate_candidate_findings
from app.risk_assessment.risk_area_resolution import resolve_risk_area_concept
from app.schemas.enterprise_intelligence import (
    ConcentrationContributorRead,
    EnterpriseAnomalyRead,
    EnterpriseAssociationRead,
    EnterpriseTrendRead,
    RecurrencePatternRead,
    RiskScoreComponentRead,
    RiskScoreRead,
)
from app.schemas.risk_assessment import (
    IntelligenceContextRead,
    RiskAreaConceptRead,
    RiskAssessmentActionFindingsRead,
    RiskAssessmentActionLinkCreate,
    RiskAssessmentActionOriginFindingRead,
    RiskAssessmentCreate,
    RiskAssessmentDetailRead,
    RiskAssessmentFindingActionCreate,
    RiskAssessmentFindingClose,
    RiskAssessmentFindingCreate,
    RiskAssessmentFindingListRead,
    RiskAssessmentFindingRead,
    RiskAssessmentFindingUpdate,
    RiskAssessmentListRead,
    RiskAssessmentRead,
    RiskAssessmentUpdate,
    RiskControlRead,
    RiskEvidenceRead,
    RiskAssessmentLinkedActionListRead,
    RiskAssessmentLinkedActionRead,
)
from app.services.audit_service import AuditAction
from app.services.permissions import Permission
from app.services.risk_assessment_service import (
    RiskAssessmentHistoryChangeType,
    assessment_mutation_transaction,
    audit_assessment_event,
    calculate_and_set_inherent_risk,
    calculate_and_set_residual_risk,
    compute_intelligence_context,
    create_finding_action_relationship,
    delete_finding_action_relationship,
    list_finding_action_relationships,
    list_findings_linked_to_action,
    normalize_as_utc,
    open_new_version,
    record_history,
    require_editable,
    require_finding_closable,
    require_finding_transition,
    require_transition,
    resolve_action_reference,
    supersede_previous_version_if_any,
    utcnow,
    validate_action_reference,
    validate_event_reference,
    validate_knowledge_document_reference,
    validate_owner_reference,
    validate_site_reference,
)
from app.services.safety_action_service import ActionHistoryChangeType
from app.services.safety_action_service import audit_action_event as _audit_safety_action_event
from app.services.safety_action_service import record_history as _record_safety_action_history

_ENDPOINT_CREATE_ASSESSMENT = "risk_assessments:create"
_ENDPOINT_CREATE_FINDING_ACTION = "risk_assessments:findings:create_action"

router = APIRouter(prefix="/risk-assessments", tags=["risk-assessments"])


def _require_permission(db: Session, context: RequestContext, *, organization_id, permission: Permission) -> None:
    """Mirrors `app/api/v1/actions.py::_require_permission()` exactly —
    used here for the SIE Milestone 27 "create action from finding"
    route, which needs a *second* permission
    (`INTERVENTION_MANAGE`/`INTERVENTION_ASSIGN`) beyond the primary
    `RISK_ASSESSMENT_WRITE` `require_context_permission()` already
    checked; `app/api/deps_context.py`'s own docstring explicitly
    sanctions calling `authorize_context()` directly for exactly this
    "non-standard permission selection" case."""
    if not authorize_context(db, context, permission=permission, organization_id=organization_id):
        detail = (
            f"API client is not authorized for organization {organization_id} or is missing "
            f"scope {permission.value}."
            if context.is_machine
            else f"Missing {permission.value} permission in the requested organization."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

_EVIDENCE_VALIDATORS = {
    RiskEvidenceType.EVENT: lambda db, organization_id, reference_id: validate_event_reference(
        db, organization_id=organization_id, event_id=reference_id
    ),
    RiskEvidenceType.ACTION: lambda db, organization_id, reference_id: validate_action_reference(
        db, organization_id=organization_id, action_id=reference_id
    ),
    RiskEvidenceType.KNOWLEDGE_DOCUMENT: lambda db, organization_id, reference_id: validate_knowledge_document_reference(
        db, organization_id=organization_id, document_id=reference_id
    ),
}


def _validate_evidence_input(db: Session, *, organization_id: uuid.UUID, evidence_items) -> None:
    for item in evidence_items:
        validator = _EVIDENCE_VALIDATORS.get(item.evidence_type)
        if validator is not None and item.reference_id is not None:
            validator(db, organization_id, item.reference_id)


def _get_owned_assessment_or_404(db: Session, *, organization_id: uuid.UUID, assessment_id: uuid.UUID) -> RiskAssessment:
    assessment = db.execute(
        select(RiskAssessment)
        .where(RiskAssessment.id == assessment_id, RiskAssessment.organization_id == organization_id)
        .options(joinedload(RiskAssessment.findings).joinedload(RiskAssessmentFinding.controls))
        .options(joinedload(RiskAssessment.findings).joinedload(RiskAssessmentFinding.evidence))
        .options(joinedload(RiskAssessment.findings).joinedload(RiskAssessmentFinding.risk_area_concept))
    ).unique().scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk assessment not found.")
    return assessment


def _get_owned_finding_or_404(
    db: Session, *, organization_id: uuid.UUID, assessment_id: uuid.UUID, finding_id: uuid.UUID
) -> RiskAssessmentFinding:
    finding = db.execute(
        select(RiskAssessmentFinding)
        .where(
            RiskAssessmentFinding.id == finding_id,
            RiskAssessmentFinding.assessment_id == assessment_id,
            RiskAssessmentFinding.organization_id == organization_id,
        )
        .options(
            joinedload(RiskAssessmentFinding.controls),
            joinedload(RiskAssessmentFinding.evidence),
            joinedload(RiskAssessmentFinding.risk_area_concept),
        )
    ).unique().scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    return finding


def _to_intelligence_context_read(result) -> IntelligenceContextRead:
    return IntelligenceContextRead(
        deterministic_risk=RiskScoreRead(
            score=result.risk.score,
            classification=result.risk.classification,
            version=result.risk.version,
            components=[RiskScoreComponentRead(**vars(c)) for c in result.risk.components],
            insufficient_data_reason=result.risk.insufficient_data_reason,
        ),
        anomalies=[EnterpriseAnomalyRead(**vars(a)) for a in result.anomalies],
        patterns=[RecurrencePatternRead(**vars(p)) for p in result.patterns],
        associations=[EnterpriseAssociationRead(**vars(a)) for a in result.associations],
        trend=EnterpriseTrendRead(**vars(result.trend)),
        concentrations=[ConcentrationContributorRead(**vars(c)) for c in result.concentrations],
        calculation_versions=result.provenance.calculation_versions,
    )


def _to_risk_area_concept_read(finding: RiskAssessmentFinding) -> RiskAreaConceptRead:
    """SIE Milestone 25A, item 18 -- assembled from the finding's own
    `risk_area_concept` relationship plus its own
    `risk_area_ontology_version` *snapshot* (never the concept's own,
    possibly since-changed, live `ontology_version` -- see
    `app/models/risk_assessment.py`'s own "historical integrity"
    docstring section). `label` is derived, not persisted (see
    `RiskAreaConceptRead`'s own docstring)."""
    concept = finding.risk_area_concept
    return RiskAreaConceptRead(
        concept_id=concept.id,
        concept_key=concept.concept_key,
        label=concept.concept_key.replace("_", " ").title(),
        layer=concept.layer,
        parent_domain=concept.parent_domain,
        ontology_version=finding.risk_area_ontology_version,
        scope="GLOBAL" if concept.organization_id is None else "ORGANIZATION",
    )


def _to_finding_read(finding: RiskAssessmentFinding) -> RiskAssessmentFindingRead:
    return RiskAssessmentFindingRead(
        id=finding.id,
        assessment_id=finding.assessment_id,
        risk_area=_to_risk_area_concept_read(finding),
        title=finding.title,
        description=finding.description,
        system_analysis_summary=finding.system_analysis_summary,
        assessor_notes=finding.assessor_notes,
        source=finding.source,
        originating_calculation_version=finding.originating_calculation_version,
        occurrence_period_start=finding.occurrence_period_start,
        occurrence_period_end=finding.occurrence_period_end,
        status=finding.status,
        candidate_status=finding.candidate_status,
        candidate_generated_at=finding.candidate_generated_at,
        likelihood=finding.likelihood,
        consequence=finding.consequence,
        inherent_risk_score=finding.inherent_risk_score,
        inherent_risk_classification=finding.inherent_risk_classification,
        residual_likelihood=finding.residual_likelihood,
        residual_consequence=finding.residual_consequence,
        residual_risk_score=finding.residual_risk_score,
        residual_risk_classification=finding.residual_risk_classification,
        inherent_risk_methodology_version=finding.inherent_risk_methodology_version,
        residual_risk_methodology_version=finding.residual_risk_methodology_version,
        linked_action_id=finding.linked_action_id,
        controls=[RiskControlRead.model_validate(c) for c in finding.controls],
        evidence=[RiskEvidenceRead.model_validate(e) for e in finding.evidence],
        created_at=finding.created_at,
        updated_at=finding.updated_at,
    )


def _to_detail_read(db: Session, assessment: RiskAssessment) -> RiskAssessmentDetailRead:
    result = compute_intelligence_context(
        db,
        organization_id=assessment.organization_id,
        scope=assessment.scope,
        site_id=assessment.site_id,
        as_of=assessment.as_of,
        window_days=assessment.window_days,
    )
    return RiskAssessmentDetailRead(
        **_assessment_fields(assessment),
        findings=[_to_finding_read(f) for f in assessment.findings],
        intelligence_context=_to_intelligence_context_read(result),
    )


def _assessment_fields(assessment: RiskAssessment) -> dict:
    return dict(
        id=assessment.id,
        organization_id=assessment.organization_id,
        scope=assessment.scope,
        site_id=assessment.site_id,
        title=assessment.title,
        reference=assessment.reference,
        assessment_type=assessment.assessment_type,
        status=assessment.status,
        lineage_id=assessment.lineage_id,
        version=assessment.version,
        supersedes_id=assessment.supersedes_id,
        assessment_date=assessment.assessment_date,
        as_of=assessment.as_of,
        window_days=assessment.window_days,
        assessor_user_id=assessment.assessor_user_id,
        methodology_version=assessment.methodology_version,
        submitted_at=assessment.submitted_at,
        submitted_by_user_id=assessment.submitted_by_user_id,
        approved_at=assessment.approved_at,
        approved_by_user_id=assessment.approved_by_user_id,
        created_by_user_id=assessment.created_by_user_id,
        created_by_api_client_id=assessment.created_by_api_client_id,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


def _to_read(assessment: RiskAssessment) -> RiskAssessmentRead:
    return RiskAssessmentRead(**_assessment_fields(assessment))


def _to_linked_action_read(
    relationship_row: RiskAssessmentFindingAction, action: SafetyAction
) -> RiskAssessmentLinkedActionRead:
    """SIE Milestone 27. Assembled from the relationship row plus the
    linked `SafetyAction`'s own current `title`/`status` -- never a
    second, persisted copy of that data (see
    `RiskAssessmentLinkedActionRead`'s own docstring)."""
    return RiskAssessmentLinkedActionRead(
        id=relationship_row.id,
        finding_id=relationship_row.finding_id,
        action_id=relationship_row.action_id,
        action_title=action.title,
        action_status=action.status.value,
        created_at=relationship_row.created_at,
        created_by_user_id=relationship_row.created_by_user_id,
        created_by_api_client_id=relationship_row.created_by_api_client_id,
    )


@router.post(
    "",
    response_model=RiskAssessmentDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_assessment(
    body: RiskAssessmentCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentDetailRead:
    if body.site_id is not None:
        validate_site_reference(db, organization_id=organization_id, site_id=body.site_id)
    if body.assessor_user_id is not None:
        validate_owner_reference(db, organization_id=organization_id, owner_user_id=body.assessor_user_id)

    as_of = normalize_as_utc(body.as_of) if body.as_of is not None else utcnow()
    window_days = body.window_days or settings.RISK_ASSESSMENT_DEFAULT_WINDOW_DAYS

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_ASSESSMENT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return RiskAssessmentDetailRead.model_validate(lookup.response_body)

    # Everything from here on -- the RiskAssessment row (and any
    # candidate findings), their RiskAssessmentHistory entries, their
    # AuditLog entry, and the IdempotencyKey response -- is one
    # transaction: all of it commits together, once, or none of it
    # persists (item 9: "the lesson from Milestone 17").
    with assessment_mutation_transaction(db):
        if body.supersedes_assessment_id is not None:
            previous = _get_owned_assessment_or_404(
                db, organization_id=organization_id, assessment_id=body.supersedes_assessment_id
            )
            assessment = open_new_version(
                db, previous=previous, created_by_user_id=context.user_id, created_by_api_client_id=context.api_client_id
            )
            assessment.title = body.title
            assessment.reference = body.reference
            assessment.assessment_type = body.assessment_type
            assessment.assessment_date = body.assessment_date
            assessment.as_of = as_of
            assessment.window_days = window_days
            assessment.assessor_user_id = body.assessor_user_id
        else:
            new_id = uuid.uuid4()
            assessment = RiskAssessment(
                id=new_id,
                organization_id=organization_id,
                scope=body.scope,
                site_id=body.site_id,
                title=body.title,
                reference=body.reference,
                assessment_type=body.assessment_type,
                status=RiskAssessmentStatus.DRAFT,
                lineage_id=new_id,
                version=1,
                supersedes_id=None,
                assessment_date=body.assessment_date,
                as_of=as_of,
                window_days=window_days,
                assessor_user_id=body.assessor_user_id,
                methodology_version=settings.RISK_ASSESSMENT_METHODOLOGY_VERSION,
                created_by_user_id=context.user_id,
                created_by_api_client_id=context.api_client_id,
            )
            db.add(assessment)
        db.flush()

        record_history(
            db,
            assessment=assessment,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_CREATED,
            to_status=assessment.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )

        if body.generate_candidates:
            compute_scope = "site" if assessment.scope == RiskAssessmentScope.SITE else "organization"
            drafts = generate_candidate_findings(
                db,
                organization_id=organization_id,
                scope=compute_scope,
                site_id=assessment.site_id if assessment.scope == RiskAssessmentScope.SITE else None,
                as_of=assessment.as_of,
                window_days=assessment.window_days,
            )
            for draft in drafts:
                finding = RiskAssessmentFinding(
                    organization_id=organization_id,
                    assessment_id=assessment.id,
                    risk_area_concept_id=draft.risk_area_concept_id,
                    risk_area_ontology_version=draft.risk_area_ontology_version,
                    title=draft.title,
                    description=draft.description,
                    system_analysis_summary=draft.system_analysis_summary,
                    source=FindingSource(draft.source),
                    originating_calculation_version=draft.originating_calculation_version,
                    occurrence_period_start=draft.occurrence_period_start,
                    occurrence_period_end=draft.occurrence_period_end,
                    candidate_status=RiskCandidateStatus.IDENTIFIED,
                    candidate_generated_at=utcnow(),
                )
                db.add(finding)
                db.flush()
                for ev in draft.evidence:
                    db.add(
                        RiskAssessmentFindingEvidence(
                            organization_id=organization_id,
                            finding_id=finding.id,
                            evidence_type=RiskEvidenceType(ev.evidence_type),
                            reference_id=ev.reference_id,
                            reference_label=ev.reference_label,
                        )
                    )
                record_history(
                    db,
                    assessment=assessment,
                    finding_id=finding.id,
                    change_type=RiskAssessmentHistoryChangeType.FINDING_CREATED,
                    changed_by_user_id=context.user_id,
                    changed_by_api_client_id=context.api_client_id,
                    request_id=request_id,
                    comment=f"System-generated candidate ({finding.source.value}).",
                )

        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_CREATED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"title": assessment.title, "scope": assessment.scope.value},
        )
        db.flush()
        db.refresh(assessment)
        result = _to_detail_read(db, assessment)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_ASSESSMENT,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.get("", response_model=RiskAssessmentListRead, dependencies=[Depends(require_rate_limit(RateLimitClass.READ))])
def list_assessments(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    status_: RiskAssessmentStatus | None = Query(default=None, alias="status"),
    scope: RiskAssessmentScope | None = Query(default=None),
    site_id: uuid.UUID | None = Query(default=None),
    lineage_id: uuid.UUID | None = Query(default=None),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_READ)),
    db: Session = Depends(get_db),
) -> RiskAssessmentListRead:
    conditions = [RiskAssessment.organization_id == organization_id]
    if status_:
        conditions.append(RiskAssessment.status == status_)
    if scope:
        conditions.append(RiskAssessment.scope == scope)
    if site_id:
        conditions.append(RiskAssessment.site_id == site_id)
    if lineage_id:
        conditions.append(RiskAssessment.lineage_id == lineage_id)

    total = db.execute(select(func.count()).select_from(RiskAssessment).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(RiskAssessment)
            .where(*conditions)
            .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return RiskAssessmentListRead(items=[_to_read(a) for a in rows], total=total, page=page, page_size=page_size)


@router.get(
    "/{assessment_id}",
    response_model=RiskAssessmentDetailRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_assessment(
    assessment_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_READ)),
    db: Session = Depends(get_db),
) -> RiskAssessmentDetailRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    return _to_detail_read(db, assessment)


@router.patch(
    "/{assessment_id}",
    response_model=RiskAssessmentRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def update_assessment(
    assessment_id: uuid.UUID,
    body: RiskAssessmentUpdate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)

    if "assessor_user_id" in body.model_fields_set and body.assessor_user_id is not None:
        validate_owner_reference(db, organization_id=organization_id, owner_user_id=body.assessor_user_id)

    changed = set()
    for field in ("title", "reference", "assessment_type", "assessment_date", "as_of", "window_days", "assessor_user_id"):
        if field in body.model_fields_set:
            new_value = getattr(body, field)
            if field == "as_of" and new_value is not None:
                new_value = normalize_as_utc(new_value)
            current_value = getattr(assessment, field)
            if field in ("as_of", "assessment_date") and current_value is not None:
                current_value = normalize_as_utc(current_value)
            if current_value != new_value:
                setattr(assessment, field, new_value)
                changed.add(field)
    if not changed:
        return _to_read(assessment)

    with assessment_mutation_transaction(db):
        db.flush()
        record_history(
            db,
            assessment=assessment,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_UPDATED,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
            comment=f"Changed fields: {', '.join(sorted(changed))}.",
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_UPDATED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"changed_fields": sorted(changed)},
        )
        result = _to_read(assessment)
    return result


@router.post(
    "/{assessment_id}/submit",
    response_model=RiskAssessmentRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def submit_assessment(
    assessment_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_transition(assessment, RiskAssessmentStatus.IN_REVIEW)

    with assessment_mutation_transaction(db):
        from_status = assessment.status.value
        assessment.status = RiskAssessmentStatus.IN_REVIEW
        assessment.submitted_at = utcnow()
        assessment.submitted_by_user_id = context.user_id
        db.flush()
        record_history(
            db,
            assessment=assessment,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_SUBMITTED,
            from_status=from_status,
            to_status=assessment.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_SUBMITTED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={},
        )
        result = _to_read(assessment)
    return result


@router.post(
    "/{assessment_id}/approve",
    response_model=RiskAssessmentRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def approve_assessment(
    assessment_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_APPROVE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_transition(assessment, RiskAssessmentStatus.APPROVED)

    with assessment_mutation_transaction(db):
        from_status = assessment.status.value
        assessment.status = RiskAssessmentStatus.APPROVED
        assessment.approved_at = utcnow()
        assessment.approved_by_user_id = context.user_id
        db.flush()
        record_history(
            db,
            assessment=assessment,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_APPROVED,
            from_status=from_status,
            to_status=assessment.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        supersede_previous_version_if_any(
            db, assessment,
            changed_by_user_id=context.user_id, changed_by_api_client_id=context.api_client_id, request_id=request_id,
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_APPROVED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={},
        )
        result = _to_read(assessment)
    return result


@router.post(
    "/{assessment_id}/archive",
    response_model=RiskAssessmentRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def archive_assessment(
    assessment_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_APPROVE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentRead:
    """SIE Milestone 26, item 1. The one manual, human-invoked retirement
    path (see `RiskAssessmentStatus.ARCHIVED`'s own docstring) --
    available from `DRAFT`/`IN_REVIEW` (abandoning an assessment that
    turned out not to be needed) or `APPROVED` (retiring one that was
    never superseded by a new version). Gated on
    `RISK_ASSESSMENT_APPROVE`, not merely `:WRITE` -- archiving is at
    least as consequential as approving (it can retire an already-
    approved risk assessment), so it is held to the same, more
    privileged permission."""
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_transition(assessment, RiskAssessmentStatus.ARCHIVED)

    with assessment_mutation_transaction(db):
        from_status = assessment.status.value
        assessment.status = RiskAssessmentStatus.ARCHIVED
        db.flush()
        record_history(
            db,
            assessment=assessment,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_ARCHIVED,
            from_status=from_status,
            to_status=assessment.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_ARCHIVED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"from_status": from_status},
        )
        result = _to_read(assessment)
    return result


@router.get(
    "/{assessment_id}/findings",
    response_model=RiskAssessmentFindingListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_findings(
    assessment_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_READ)),
    db: Session = Depends(get_db),
) -> RiskAssessmentFindingListRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    return RiskAssessmentFindingListRead(
        items=[_to_finding_read(f) for f in assessment.findings], total=len(assessment.findings)
    )


@router.post(
    "/{assessment_id}/findings",
    response_model=RiskAssessmentFindingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_finding(
    assessment_id: uuid.UUID,
    body: RiskAssessmentFindingCreate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentFindingRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    _validate_evidence_input(db, organization_id=organization_id, evidence_items=body.evidence)
    risk_area_concept = resolve_risk_area_concept(
        db, organization_id=organization_id, concept_id=body.risk_area_concept_id
    )

    with assessment_mutation_transaction(db):
        finding = RiskAssessmentFinding(
            organization_id=organization_id,
            assessment_id=assessment.id,
            risk_area_concept_id=risk_area_concept.id,
            risk_area_ontology_version=risk_area_concept.ontology_version,
            title=body.title,
            description=body.description,
            assessor_notes=body.assessor_notes,
            source=body.source,
            occurrence_period_start=body.occurrence_period_start,
            occurrence_period_end=body.occurrence_period_end,
            candidate_status=None,  # directly human-authored -- never subject to candidate review
        )
        db.add(finding)
        db.flush()
        if body.likelihood is not None and body.consequence is not None:
            calculate_and_set_inherent_risk(finding, likelihood=body.likelihood, consequence=body.consequence)
        for ev in body.evidence:
            db.add(
                RiskAssessmentFindingEvidence(
                    organization_id=organization_id,
                    finding_id=finding.id,
                    evidence_type=ev.evidence_type,
                    reference_id=ev.reference_id,
                    reference_label=ev.reference_label,
                )
            )
        db.flush()
        record_history(
            db,
            assessment=assessment,
            finding_id=finding.id,
            change_type=RiskAssessmentHistoryChangeType.FINDING_CREATED,
            to_status=finding.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_FINDING_CREATED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"finding_id": str(finding.id), "risk_area_concept_id": str(finding.risk_area_concept_id)},
        )
        db.refresh(finding)
        result = _to_finding_read(finding)
    return result


@router.patch(
    "/{assessment_id}/findings/{finding_id}",
    response_model=RiskAssessmentFindingRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def update_finding(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: RiskAssessmentFindingUpdate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentFindingRead:
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )

    supplied = body.model_fields_set
    if not supplied:
        return _to_finding_read(finding)

    if body.evidence_add:
        _validate_evidence_input(db, organization_id=organization_id, evidence_items=body.evidence_add)
    if "linked_action_id" in supplied and body.linked_action_id is not None:
        validate_action_reference(db, organization_id=organization_id, action_id=body.linked_action_id)

    # SIE Milestone 27, "closure governance": CLOSED is reachable only
    # through the dedicated POST .../findings/{finding_id}/close route
    # (require_finding_closable()'s own gate) -- this generic field never
    # accepts it, so there is exactly one, governed path to closure. See
    # FindingStatus's own docstring.
    if "status" in supplied and body.status == FindingStatus.CLOSED and finding.status != FindingStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A finding cannot be closed via this generic update -- use "
            "POST .../findings/{finding_id}/close, which requires an explicit closure_reason.",
        )

    # Item 15/27: a rating may only ever be set on a non-candidate or an
    # ACCEPTED candidate -- never on IDENTIFIED/UNDER_REVIEW/REJECTED.
    # The effective candidate_status after this update is either the one
    # just supplied, or the finding's own current one if not touched.
    effective_candidate_status = body.candidate_status if "candidate_status" in supplied else finding.candidate_status
    wants_rating = "likelihood" in supplied and body.likelihood is not None
    if wants_rating and not (effective_candidate_status is None or effective_candidate_status == RiskCandidateStatus.ACCEPTED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A likelihood/consequence rating may only be set once a candidate is ACCEPTED (or for a "
            "non-candidate finding) -- candidate != approved risk.",
        )

    # Captured before mutation so the history/audit entries below record
    # what genuinely changed (SIE Milestone 26, item 8's own "Finding
    # risk rating changed"/"Finding linked/unlinked to action").
    previous_status = finding.status.value
    previous_inherent_classification = finding.inherent_risk_classification
    previous_residual_classification = finding.residual_risk_classification
    previous_linked_action_id = finding.linked_action_id

    with assessment_mutation_transaction(db):
        general_fields_changed = set()
        for field in ("title", "description", "assessor_notes", "status"):
            if field in supplied:
                new_value = getattr(body, field)
                if getattr(finding, field) != new_value:
                    setattr(finding, field, new_value)
                    general_fields_changed.add(field)
        if "candidate_status" in supplied and finding.candidate_status != body.candidate_status:
            finding.candidate_status = body.candidate_status
            general_fields_changed.add("candidate_status")

        rated_inherent = False
        if "likelihood" in supplied and body.likelihood is not None:
            calculate_and_set_inherent_risk(finding, likelihood=body.likelihood, consequence=body.consequence)
            rated_inherent = True
        rated_residual = False
        if "residual_likelihood" in supplied and body.residual_likelihood is not None:
            calculate_and_set_residual_risk(
                finding, likelihood=body.residual_likelihood, consequence=body.residual_consequence
            )
            rated_residual = True

        if body.controls is not None:
            finding.controls = [
                RiskAssessmentControl(
                    organization_id=organization_id,
                    finding_id=finding.id,
                    description=c.description,
                    control_type=c.control_type,
                    status=c.status,
                    owner_user_id=c.owner_user_id,
                    reference=c.reference,
                    effectiveness=c.effectiveness,
                )
                for c in body.controls
            ]
            general_fields_changed.add("controls")
        if body.evidence_add:
            for ev in body.evidence_add:
                db.add(
                    RiskAssessmentFindingEvidence(
                        organization_id=organization_id,
                        finding_id=finding.id,
                        evidence_type=ev.evidence_type,
                        reference_id=ev.reference_id,
                        reference_label=ev.reference_label,
                    )
                )
            general_fields_changed.add("evidence")

        action_linked = action_unlinked = False
        if "linked_action_id" in supplied and previous_linked_action_id != body.linked_action_id:
            finding.linked_action_id = body.linked_action_id
            action_linked = body.linked_action_id is not None
            action_unlinked = body.linked_action_id is None
            # SIE Milestone 27: keep the new relationship table in sync so
            # a finding linked only through this legacy field is still
            # visible via GET .../findings/{finding_id}/actions -- see
            # app/models/risk_assessment_finding_action.py's own docstring.
            if action_linked:
                create_finding_action_relationship(
                    db, finding=finding, action_id=body.linked_action_id,
                    changed_by_user_id=context.user_id, changed_by_api_client_id=context.api_client_id,
                )
            if action_unlinked and previous_linked_action_id is not None:
                delete_finding_action_relationship(
                    db, finding_id=finding.id, action_id=previous_linked_action_id
                )

        db.flush()

        if general_fields_changed:
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=RiskAssessmentHistoryChangeType.FINDING_UPDATED,
                from_status=previous_status,
                to_status=finding.status.value,
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
                comment=f"Changed fields: {', '.join(sorted(general_fields_changed))}.",
            )
            audit_assessment_event(
                db,
                action_name=AuditAction.RISK_ASSESSMENT_FINDING_UPDATED,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={"finding_id": str(finding.id), "changed_fields": sorted(general_fields_changed)},
            )
        if rated_inherent:
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=RiskAssessmentHistoryChangeType.FINDING_RISK_RATED,
                from_status=previous_inherent_classification,
                to_status=finding.inherent_risk_classification,
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
            )
            audit_assessment_event(
                db,
                action_name=AuditAction.RISK_ASSESSMENT_FINDING_RISK_RATED,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={
                    "finding_id": str(finding.id), "likelihood": finding.likelihood, "consequence": finding.consequence,
                    "inherent_risk_classification": finding.inherent_risk_classification,
                },
            )
        if rated_residual:
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=RiskAssessmentHistoryChangeType.FINDING_RESIDUAL_RATED,
                from_status=previous_residual_classification,
                to_status=finding.residual_risk_classification,
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
            )
            audit_assessment_event(
                db,
                action_name=AuditAction.RISK_ASSESSMENT_FINDING_RISK_RATED,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={
                    "finding_id": str(finding.id), "residual_likelihood": finding.residual_likelihood,
                    "residual_consequence": finding.residual_consequence,
                    "residual_risk_classification": finding.residual_risk_classification,
                },
            )
        if action_linked or action_unlinked:
            change_type = (
                RiskAssessmentHistoryChangeType.FINDING_ACTION_LINKED
                if action_linked
                else RiskAssessmentHistoryChangeType.FINDING_ACTION_UNLINKED
            )
            audit_action_name = (
                AuditAction.RISK_ASSESSMENT_FINDING_ACTION_LINKED
                if action_linked
                else AuditAction.RISK_ASSESSMENT_FINDING_ACTION_UNLINKED
            )
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=change_type,
                from_status=str(previous_linked_action_id) if previous_linked_action_id else None,
                to_status=str(finding.linked_action_id) if finding.linked_action_id else None,
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
            )
            audit_assessment_event(
                db,
                action_name=audit_action_name,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={"finding_id": str(finding.id), "linked_action_id": str(finding.linked_action_id) if finding.linked_action_id else None},
            )

        db.refresh(finding)
        result = _to_finding_read(finding)
    return result


# --- Finding <-> Action relationship (SIE Milestone 27) -------------------------------------


@router.post(
    "/{assessment_id}/findings/{finding_id}/actions",
    response_model=RiskAssessmentLinkedActionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_finding_action(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: RiskAssessmentFindingActionCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentLinkedActionRead:
    """SIE Milestone 27, item 1: "Create an action from a finding." Creates
    a brand-new `SafetyAction` -- this route's own, risk-assessment-
    domain-scoped creation path (`app/api/v1/actions.py::POST /actions`
    is untouched and remains the general-purpose one) -- and links it to
    this finding in the same transaction. Requires `RISK_ASSESSMENT_WRITE`
    (to mutate the finding) *and* `INTERVENTION_MANAGE` (to create the
    action itself, `+INTERVENTION_ASSIGN` if `owner_user_id` is supplied)
    -- creating an action is an Actions-domain capability that
    risk-assessment write access alone never grants, mirroring item 29's
    own "risk_assessment:write != governance:manage" precedent one
    boundary over. The new action's origin is recorded in its own
    `attributes` (`app/models/safety_action.py`'s own documented
    "bounded, domain-specific structured data... don't force a migration
    for every new field" extension point) -- never a new column on
    `SafetyAction` itself, which stays completely unmodified by this
    milestone."""
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )
    _require_permission(db, context, organization_id=organization_id, permission=Permission.INTERVENTION_MANAGE)
    if body.owner_user_id is not None:
        _require_permission(db, context, organization_id=organization_id, permission=Permission.INTERVENTION_ASSIGN)
        validate_owner_reference(db, organization_id=organization_id, owner_user_id=body.owner_user_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_FINDING_ACTION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return RiskAssessmentLinkedActionRead.model_validate(lookup.response_body)

    with assessment_mutation_transaction(db):
        action = SafetyAction(
            organization_id=organization_id,
            title=body.title,
            description=body.description,
            action_type=body.action_type,
            priority=body.priority,
            status=ActionStatus.OPEN,
            owner_user_id=body.owner_user_id,
            due_date=body.due_date,
            created_by_user_id=context.user_id,
            created_by_api_client_id=context.api_client_id,
            external_reference=body.external_reference,
            attributes={
                "risk_assessment_origin": {"assessment_id": str(assessment.id), "finding_id": str(finding.id)}
            },
        )
        db.add(action)
        db.flush()

        # The action's own domain trail (app/services/safety_action_service.py)
        # -- reused, not duplicated, so this action's own history/audit
        # is identical regardless of which endpoint created it.
        _record_safety_action_history(
            db,
            action=action,
            change_type=ActionHistoryChangeType.CREATED,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
            commit=False,
        )
        _audit_safety_action_event(
            db,
            action_name=AuditAction.SAFETY_ACTION_CREATED,
            action=action,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={
                "source": "risk_assessment_finding", "finding_id": str(finding.id), "assessment_id": str(assessment.id),
            },
            commit=False,
        )

        relationship_row, _created = create_finding_action_relationship(
            db, finding=finding, action_id=action.id,
            changed_by_user_id=context.user_id, changed_by_api_client_id=context.api_client_id,
        )
        record_history(
            db,
            assessment=assessment,
            finding_id=finding.id,
            change_type=RiskAssessmentHistoryChangeType.FINDING_ACTION_CREATED,
            to_status=str(action.id),
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
            comment=f"Created action {action.id!s} ({action.title!r}) as the response to this finding.",
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_FINDING_ACTION_CREATED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"finding_id": str(finding.id), "action_id": str(action.id)},
        )
        db.refresh(action)
        result = _to_linked_action_read(relationship_row, action)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_FINDING_ACTION,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.post(
    "/{assessment_id}/findings/{finding_id}/actions/link",
    response_model=RiskAssessmentLinkedActionRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def link_finding_action(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: RiskAssessmentActionLinkCreate,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentLinkedActionRead:
    """SIE Milestone 27, item 1: "Link an existing action to a finding."
    Idempotent by construction (`create_finding_action_relationship()`'s
    own contract) -- linking an already-linked action returns the
    existing relationship, `200`, rather than erroring or duplicating
    it; no `Idempotency-Key` machinery is needed for an operation that is
    already safely retryable by nature (contrast `create_finding_action()`
    above, a genuine "create a new resource" `POST`)."""
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )
    action = resolve_action_reference(db, organization_id=organization_id, action_id=body.action_id)

    with assessment_mutation_transaction(db):
        relationship_row, created = create_finding_action_relationship(
            db, finding=finding, action_id=action.id,
            changed_by_user_id=context.user_id, changed_by_api_client_id=context.api_client_id,
        )
        if created:
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=RiskAssessmentHistoryChangeType.FINDING_ACTION_LINKED,
                to_status=str(action.id),
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
            )
            audit_assessment_event(
                db,
                action_name=AuditAction.RISK_ASSESSMENT_FINDING_ACTION_LINKED,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={"finding_id": str(finding.id), "action_id": str(action.id)},
            )
        result = _to_linked_action_read(relationship_row, action)
    return result


@router.delete(
    "/{assessment_id}/findings/{finding_id}/actions/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def unlink_finding_action(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    action_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> Response:
    """SIE Milestone 27, item 1: "Unlink an action." Idempotent: unlinking
    an action that isn't currently linked is a `204` no-op, not a `404`
    -- a retried unlink call must never fail merely because an earlier
    attempt already succeeded (item 10's own "safely retryable")."""
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )

    with assessment_mutation_transaction(db):
        deleted = delete_finding_action_relationship(db, finding_id=finding.id, action_id=action_id)
        if deleted:
            # SIE Milestone 27: keep the legacy linked_action_id column in
            # sync too, the same direction update_finding()'s own
            # linked_action_id branch already keeps it -- unlinking an
            # action through this new endpoint must not leave the legacy
            # field silently pointing at an action that is no longer
            # actually linked.
            if finding.linked_action_id == action_id:
                finding.linked_action_id = None
                db.flush()
            record_history(
                db,
                assessment=assessment,
                finding_id=finding.id,
                change_type=RiskAssessmentHistoryChangeType.FINDING_ACTION_UNLINKED,
                from_status=str(action_id),
                changed_by_user_id=context.user_id,
                changed_by_api_client_id=context.api_client_id,
                request_id=request_id,
            )
            audit_assessment_event(
                db,
                action_name=AuditAction.RISK_ASSESSMENT_FINDING_ACTION_UNLINKED,
                assessment=assessment,
                user_id=context.user_id,
                caller_kind=context.kind,
                metadata={"finding_id": str(finding.id), "action_id": str(action_id)},
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{assessment_id}/findings/{finding_id}/actions",
    response_model=RiskAssessmentLinkedActionListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_finding_actions(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_READ)),
    db: Session = Depends(get_db),
) -> RiskAssessmentLinkedActionListRead:
    """SIE Milestone 27, item 1: "View all actions associated with a
    finding" -- every `SafetyAction` currently linked to this finding
    (there may be more than one; a serious risk may require several
    controls/actions, this milestone's own explicit rationale for a real
    relationship table over the single `linked_action_id` pointer)."""
    _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )
    rows = list_finding_action_relationships(db, finding_id=finding.id)
    action_ids = [r.action_id for r in rows]
    actions_by_id = {}
    if action_ids:
        actions_by_id = {
            a.id: a for a in db.execute(select(SafetyAction).where(SafetyAction.id.in_(action_ids))).scalars().all()
        }
    items = [_to_linked_action_read(r, actions_by_id[r.action_id]) for r in rows if r.action_id in actions_by_id]
    return RiskAssessmentLinkedActionListRead(items=items, total=len(items))


@router.post(
    "/{assessment_id}/findings/{finding_id}/close",
    response_model=RiskAssessmentFindingRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def close_finding(
    assessment_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: RiskAssessmentFindingClose,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_APPROVE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> RiskAssessmentFindingRead:
    """SIE Milestone 27, item 6/"closure governance": the one, governed
    path to `FindingStatus.CLOSED` (see that enum's own docstring and
    `require_finding_closable()`'s own). Gated on `RISK_ASSESSMENT_APPROVE`,
    not merely `:WRITE` -- closing a finding is consequential enough to
    hold to the same, more privileged permission `archive`/`approve`
    already require. Deliberately never triggered by a linked action's
    own status (see `require_finding_closable()`'s own docstring for the
    milestone's explicit "that would be unsafe" example this avoids)."""
    assessment = _get_owned_assessment_or_404(db, organization_id=organization_id, assessment_id=assessment_id)
    require_editable(assessment)
    finding = _get_owned_finding_or_404(
        db, organization_id=organization_id, assessment_id=assessment_id, finding_id=finding_id
    )
    require_finding_transition(finding, FindingStatus.CLOSED)
    require_finding_closable(finding, closure_reason=body.closure_reason)

    with assessment_mutation_transaction(db):
        from_status = finding.status.value
        finding.status = FindingStatus.CLOSED
        db.flush()
        record_history(
            db,
            assessment=assessment,
            finding_id=finding.id,
            change_type=RiskAssessmentHistoryChangeType.FINDING_CLOSED,
            from_status=from_status,
            to_status=finding.status.value,
            changed_by_user_id=context.user_id,
            changed_by_api_client_id=context.api_client_id,
            request_id=request_id,
            comment=body.closure_reason,
        )
        audit_assessment_event(
            db,
            action_name=AuditAction.RISK_ASSESSMENT_FINDING_CLOSED,
            assessment=assessment,
            user_id=context.user_id,
            caller_kind=context.kind,
            metadata={"finding_id": str(finding.id), "closure_reason": body.closure_reason},
        )
        db.refresh(finding)
        result = _to_finding_read(finding)
    return result


@router.get(
    "/actions/{action_id}/findings",
    response_model=RiskAssessmentActionFindingsRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_action_findings(
    action_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.RISK_ASSESSMENT_READ)),
    db: Session = Depends(get_db),
) -> RiskAssessmentActionFindingsRead:
    """SIE Milestone 27, item 1: "View the originating finding from an
    action" / action -> finding navigation -- every finding *currently*
    linked to this action, tenant-scoped to the caller's own
    organization. An action id from a foreign organization (or one that
    does not exist at all) simply has no findings linked to it *in this
    organization* -- an empty list, not a `404`, consistent with every
    other read in this module never disclosing a foreign record's
    existence one way or the other."""
    findings = list_findings_linked_to_action(db, action_id=action_id, organization_id=organization_id)
    return RiskAssessmentActionFindingsRead(
        action_id=action_id,
        findings=[RiskAssessmentActionOriginFindingRead.model_validate(f) for f in findings],
    )


__all__ = ["router"]
