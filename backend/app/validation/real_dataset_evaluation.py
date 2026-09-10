"""Real dataset evaluation runner — SIE Real Enterprise Dataset Evaluation
v0.1.

Orchestrates, and adds no analytical logic beyond, the existing SIE
pipeline:

    load_real_dataset()                                  [app/validation/real_dataset_loader.py]
        -> Organization + one Site per distinct project name  (real, unmodified models)
        -> run_enterprise_dataset_validation()             [app/validation/enterprise_dataset_validation.py,
                                                              UNCHANGED — covers items 2, 3/6, 4/8, 5/9, 6/10, 7/12]
        -> observation-vs-incident temporal analysis        [item 11 — NEW orchestration below,
                                                              composing only events_as_of() calls
                                                              (app/intelligence/temporal.py, UNCHANGED)
                                                              in the same bucketing shape
                                                              bucketed_counts() already uses; no new
                                                              analytical algorithm]
        -> queue_review_candidates()                        [item 15, UNCHANGED]
        -> to_dict() / to_markdown()                        [items 13/14, extends app/validation/report.py's
                                                              own rendering rather than duplicating it]

This module never trains a model, never adds a new terminology alias,
never invents a threshold, and never claims a correlation is a cause —
see `_TEMPORAL_ANALYSIS_METHODOLOGY_NOTE` below, which every rendered
report restates verbatim.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.temporal import events_as_of, utcnow
from app.models.organization import Organization
from app.models.site import Site
from app.validation.enterprise_dataset_validation import (
    EnterpriseDatasetValidationReport,
    queue_review_candidates,
    run_enterprise_dataset_validation,
)
from app.validation.real_dataset_loader import (
    StructureValidationIssue,
    load_real_dataset,
)
from app.validation.report import to_dict as _validation_to_dict
from app.validation.report import to_markdown as _validation_to_markdown

# --- Organization / Site construction -----------------------------------------------------------


def build_organization_and_sites(
    db: Session, *, organization_name: str, project_names: set[str] | list[str]
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Creates one real, unmodified `Organization` row representing this
    evaluation, and one real `Site` row per **distinct project name the
    workbook itself contains** — never a synthetic project, never
    collapsed into a single site. Site/project-scoped predictive
    readiness (item 12) and the observation-vs-incident temporal
    analysis (item 11) both require genuine per-site rows to be
    meaningful; a single shared site would silently blend every
    project's history together, which is exactly the kind of assumption
    this evaluation must not make."""
    org = Organization(name=organization_name)
    db.add(org)
    db.commit()

    project_to_site_id: dict[str, uuid.UUID] = {}
    for project_name in sorted(project_names):
        site = Site(organization_id=org.id, name=project_name)
        db.add(site)
        db.flush()
        project_to_site_id[project_name] = site.id
    db.commit()

    return org.id, project_to_site_id


def assign_site_ids(payloads: list[RawSafetyEventPayload], project_to_site_id: dict[str, uuid.UUID]) -> None:
    """Stamps `site_id` onto each payload by exact-match lookup of its
    own `project` string — never a fuzzy or partial match, and a payload
    whose `project` is missing or not in `project_to_site_id` is left
    with `site_id=None` (never guessed, and still ingested — the
    existing validation pipeline reports a missing site as-is)."""
    for payload in payloads:
        if payload.project and payload.project in project_to_site_id:
            payload.site_id = project_to_site_id[payload.project]


# --- Item 11: observation-vs-incident temporal analysis -----------------------------------------

_TEMPORAL_ANALYSIS_METHODOLOGY_NOTE = (
    "Descriptive co-occurrence only. Each bucket below reports how many OBSERVATION events and "
    "how many incident-sheet events (any raw Incident Type) fell in the same site/time window, "
    "computed from the exact same events_as_of() query builder "
    "(app/intelligence/temporal.py, UNCHANGED) every other trend calculation in this codebase "
    "uses. This is NOT a correlation coefficient, NOT a statistical test, and NOT a causal claim "
    "-- a project with observations and incidents in the same period is not thereby shown to have "
    "one cause the other. See the task's own explicit instruction: 'same-project observation + "
    "incident = causal relationship' must not be assumed. Deliberately RETROSPECTIVE, not "
    "point-in-time: it queries every accepted canonical event by event_time alone "
    "(events_as_of(..., strict_point_in_time=False)), not gated by ingestion_time -- the "
    "'what did this dataset's own history actually contain' question TemporalIntegrityReport's "
    "own retrospective-vs-point-in-time note already distinguishes from a live feature "
    "computation. A strict point-in-time reading (ingestion_time <= as_of) of a real dataset "
    "that was bulk-ingested just now would, correctly, show ~zero events in every bucket except "
    "the most recent -- the same 'bulk backfill collapses into the most recent bucket' behavior "
    "already documented from Milestone 2, reconfirmed against this real dataset, not a bug in "
    "this analysis. Using it here would answer a different question than the one item 11 asks."
)


@dataclass
class ObservationIncidentTemporalBucket:
    period_start: datetime
    period_end: datetime
    observation_count: int
    incident_count: int


@dataclass
class SiteObservationIncidentTemporalAnalysis:
    site_id: uuid.UUID
    project_name: str
    buckets: list[ObservationIncidentTemporalBucket] = field(default_factory=list)
    total_observations: int = 0
    total_incidents: int = 0


@dataclass
class ObservationIncidentTemporalAnalysisReport:
    as_of: datetime
    period_days: int
    num_periods: int
    per_site: list[SiteObservationIncidentTemporalAnalysis] = field(default_factory=list)
    methodology_note: str = _TEMPORAL_ANALYSIS_METHODOLOGY_NOTE


def _retrospective_bucketed_counts(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
    period_end: datetime,
    period_days: int,
    num_periods: int,
    predicate=None,
) -> list[tuple[datetime, datetime, int]]:
    """The exact same `num_periods` consecutive, non-overlapping,
    `period_days`-length bucketing loop as `bucketed_counts()`
    (`app/intelligence/temporal.py`, unchanged) — reimplemented at this
    one call site only because `bucketed_counts()` does not expose
    `events_as_of()`'s own `strict_point_in_time` parameter, and item
    11's own question ("what did this dataset's history actually
    contain") is deliberately the RETROSPECTIVE one, not the
    point-in-time one — see `_TEMPORAL_ANALYSIS_METHODOLOGY_NOTE`. Every
    other clause (tenant scoping, quality-status filtering, event_time
    bounds) is still `events_as_of()` itself, unchanged."""
    buckets: list[tuple[datetime, datetime, int]] = []
    bucket_end = period_end
    for _ in range(num_periods):
        bucket_start = bucket_end - timedelta(days=period_days)
        query = events_as_of(
            organization_id=organization_id, as_of=bucket_end, window_start=bucket_start, site_id=site_id,
            strict_point_in_time=False,
        )
        events = db.execute(query).scalars().all()
        count = sum(1 for e in events if predicate(e)) if predicate else len(events)
        buckets.append((bucket_start, bucket_end, count))
        bucket_end = bucket_start
    buckets.reverse()
    return buckets


def _analyze_observation_incident_temporal(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id_to_project: dict[uuid.UUID, str],
    as_of: datetime,
    period_days: int = 30,
    num_periods: int = 8,
) -> ObservationIncidentTemporalAnalysisReport:
    """Item 11. Per site, buckets OBSERVATION events against
    incident-sheet events into the same `period_days`-length windows
    ending at `as_of`, using `_retrospective_bucketed_counts()` above.

    The incident side is matched as "usable, non-OBSERVATION event_type"
    rather than by the raw source `Incident Type` terms — deliberately,
    not as a guess: `events_as_of()` reads `SafetyEvent.event_type`
    **after** terminology mapping has already run, so a MAPPED incident
    term (e.g. "Injury") is stored under its *canonical* form, not the
    raw loader term; matching the raw term here would silently miss
    every successfully mapped incident. Since `real_dataset_loader.py`
    sets `event_type="OBSERVATION"` literally and only for
    Observation-sheet rows (see that module's own docstring), "not
    OBSERVATION" is a structural fact about this dataset, not an
    assumption. An UNKNOWN/AMBIGUOUS incident term is QUARANTINED by
    ingestion and so, correctly, does not appear in either series —
    `events_as_of()` excludes quarantined records by default, the same
    "held out until reviewed" rule every other analytics call in this
    codebase already follows.

    Both series share identical bucket boundaries by construction (same
    `period_end`/`period_days`/`num_periods` arguments), so they are
    directly comparable side-by-side — comparable, not causally linked;
    see `_TEMPORAL_ANALYSIS_METHODOLOGY_NOTE`."""
    report = ObservationIncidentTemporalAnalysisReport(as_of=as_of, period_days=period_days, num_periods=num_periods)

    for site_id, project_name in sorted(site_id_to_project.items(), key=lambda kv: kv[1]):
        observation_buckets = _retrospective_bucketed_counts(
            db, organization_id=organization_id, site_id=site_id, period_end=as_of,
            period_days=period_days, num_periods=num_periods,
            predicate=lambda e: e.event_type == "OBSERVATION",
        )
        incident_buckets = _retrospective_bucketed_counts(
            db, organization_id=organization_id, site_id=site_id, period_end=as_of,
            period_days=period_days, num_periods=num_periods,
            predicate=lambda e: e.event_type != "OBSERVATION",
        )

        buckets = [
            ObservationIncidentTemporalBucket(
                period_start=obs_start, period_end=obs_end, observation_count=obs_count, incident_count=inc_count,
            )
            for (obs_start, obs_end, obs_count), (_, _, inc_count) in zip(observation_buckets, incident_buckets, strict=True)
        ]
        report.per_site.append(
            SiteObservationIncidentTemporalAnalysis(
                site_id=site_id, project_name=project_name, buckets=buckets,
                total_observations=sum(b.observation_count for b in buckets),
                total_incidents=sum(b.incident_count for b in buckets),
            )
        )

    return report


# --- Top-level entry point -----------------------------------------------------------------------


@dataclass
class RealDatasetEvaluationReport:
    label: str
    organization_id: uuid.UUID
    generated_at: datetime
    workbook_structure_issues: list[StructureValidationIssue]
    row_level_skips: list[str]
    incident_sheet_row_count: int
    observation_sheet_row_count: int
    project_to_site_id: dict[str, str]
    validation: EnterpriseDatasetValidationReport
    observation_incident_temporal: ObservationIncidentTemporalAnalysisReport
    queued_review_candidate_count: int


def run_real_dataset_evaluation(
    db: Session,
    *,
    workbook_path: str | Path,
    organization_name: str,
    label: str,
    as_of: datetime | None = None,
    use_terminology_mapping: bool = True,
    period_days: int = 30,
    num_periods: int = 8,
) -> RealDatasetEvaluationReport:
    """The full evaluation, end to end. `workbook_path` is read once,
    locally, by `load_real_dataset()` — never embedded, never committed
    (see that module's own docstring). `label` is mandatory and
    caller-supplied, exactly like `run_enterprise_dataset_validation()`'s
    own `label` contract, so a real-data report can never be mistaken
    for a synthetic one or vice versa."""
    load_result = load_real_dataset(workbook_path)

    org_id, project_to_site_id = build_organization_and_sites(
        db, organization_name=organization_name, project_names=load_result.distinct_project_names
    )
    assign_site_ids(load_result.all_payloads, project_to_site_id)

    # `as_of` is passed straight through to `run_enterprise_dataset_validation()`
    # UNTOUCHED -- when the caller leaves it `None`, that call captures its
    # OWN `utcnow()` internally, *after* `ingest_batch()` has actually run
    # and stamped every row's `ingestion_time` (see that function's own
    # docstring on exactly this hazard). Capturing an `analysis_as_of` up
    # here and passing it down as an explicit `as_of` would freeze it
    # *before* ingestion happens, making `ingestion_time <= as_of` false
    # for every just-ingested row -- a real bug caught by this milestone's
    # own smoke test (every event_time-based check came back empty against
    # the real workbook) before this comment existed. So: pass `as_of`
    # through unchanged, and capture this module's own `analysis_as_of`
    # strictly *after* that call returns -- guaranteed >= whatever
    # `run_enterprise_dataset_validation()` used internally, so the
    # observation-vs-incident temporal analysis below can only see the
    # same-or-more of what was actually ingested, never less.
    validation_report = run_enterprise_dataset_validation(
        db, organization_id=org_id, payloads=load_result.all_payloads, label=label,
        site_ids=list(project_to_site_id.values()), as_of=as_of,
        use_terminology_mapping=use_terminology_mapping,
    )
    analysis_as_of = as_of if as_of is not None else utcnow()

    site_id_to_project = {site_id: project for project, site_id in project_to_site_id.items()}
    observation_incident_temporal = _analyze_observation_incident_temporal(
        db, organization_id=org_id, site_id_to_project=site_id_to_project,
        as_of=analysis_as_of, period_days=period_days, num_periods=num_periods,
    )

    queued = queue_review_candidates(db, organization_id=org_id, report=validation_report)

    return RealDatasetEvaluationReport(
        label=label,
        organization_id=org_id,
        generated_at=utcnow(),
        workbook_structure_issues=load_result.structure_issues,
        row_level_skips=load_result.row_level_skips,
        incident_sheet_row_count=load_result.incident_sheet_row_count,
        observation_sheet_row_count=load_result.observation_sheet_row_count,
        project_to_site_id={name: str(site_id) for name, site_id in project_to_site_id.items()},
        validation=validation_report,
        observation_incident_temporal=observation_incident_temporal,
        queued_review_candidate_count=len(queued),
    )


# --- Items 13/14: machine-readable / human-readable rendering ------------------------------------


def to_dict(report: RealDatasetEvaluationReport) -> dict:
    """The machine-readable form (item 13) — a plain, JSON-serializable
    dict. Extends `app.validation.report.to_dict()`'s own rendering of
    the wrapped `EnterpriseDatasetValidationReport` rather than
    reimplementing it."""
    return {
        "label": report.label,
        "organization_id": str(report.organization_id),
        "generated_at": report.generated_at.isoformat(),
        "workbook_structure_issues": [dataclasses.asdict(i) for i in report.workbook_structure_issues],
        "row_level_skips": report.row_level_skips,
        "incident_sheet_row_count": report.incident_sheet_row_count,
        "observation_sheet_row_count": report.observation_sheet_row_count,
        "project_to_site_id": report.project_to_site_id,
        "validation": _validation_to_dict(report.validation),
        "observation_incident_temporal": dataclasses.asdict(report.observation_incident_temporal),
        "queued_review_candidate_count": report.queued_review_candidate_count,
    }


def to_markdown(report: RealDatasetEvaluationReport) -> str:
    """The human-readable form (item 14) — the wrapped validation
    report's own OBSERVED/MAPPED/QUARANTINED/REJECTED/UNAVAILABLE
    sections (`app.validation.report.to_markdown()`, unchanged), plus
    this module's own workbook-loading and observation-vs-incident
    temporal-analysis sections."""
    oit = report.observation_incident_temporal
    lines = [
        "# Real Enterprise Dataset Evaluation Report",
        "",
        f"**{report.label}**",
        "",
        f"- Organization: `{report.organization_id}`",
        f"- Generated: {report.generated_at.isoformat()}",
        f"- Projects mapped to sites: {len(report.project_to_site_id)}",
        "",
        "## Workbook loading",
        "",
        f"- Incident sheet data rows: {report.incident_sheet_row_count}",
        f"- Observation sheet data rows: {report.observation_sheet_row_count}",
        f"- Structural issues: {[dataclasses.asdict(i) for i in report.workbook_structure_issues] or 'none'}",
        f"- Row-level mapping skips: {len(report.row_level_skips)}",
        "",
        _validation_to_markdown(report.validation),
        "## Observation-vs-incident temporal analysis (item 11)",
        "",
        f"> {oit.methodology_note}",
        "",
        f"- Window: {oit.num_periods} x {oit.period_days}-day period(s) ending {oit.as_of.isoformat()}",
        "",
    ]
    for site in oit.per_site:
        lines.append(f"### {site.project_name}")
        lines.append("")
        lines.append(f"- Total observations: {site.total_observations} | Total incidents: {site.total_incidents}")
        lines.append("")
        lines.append("| period_start | period_end | observations | incidents |")
        lines.append("|---|---|---|---|")
        for bucket in site.buckets:
            lines.append(
                f"| {bucket.period_start.date().isoformat()} | {bucket.period_end.date().isoformat()} "
                f"| {bucket.observation_count} | {bucket.incident_count} |"
            )
        lines.append("")

    lines.append("## HSE expert review")
    lines.append("")
    lines.append(f"- Review candidates queued: {report.queued_review_candidate_count}")
    lines.append("")
    return "\n".join(lines)
