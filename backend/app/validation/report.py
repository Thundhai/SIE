"""Machine-readable and human-readable rendering for an
`EnterpriseDatasetValidationReport` — Real Enterprise Dataset Validation
Foundation v0.1, item 10.

The human-readable render is organized around the five sections item 10
requires, kept strictly separate so a reader never conflates them:

* **OBSERVED** — what the dataset actually contains, before any
  validation decision.
* **MAPPED** — what SIE successfully normalized (VALID + PARTIAL).
* **QUARANTINED** — what SIE deliberately refused to interpret (stored,
  but held out of every analytics/feature/signal calculation).
* **REJECTED** — what failed ingestion outright (no canonical event).
* **UNAVAILABLE** — what cannot be evaluated because the dataset does
  not contain the required information (an unelapsed prediction
  horizon, a site excluded from predictive readiness, a feature this
  harness had no data to compute).

**Missing data is never interpreted as evidence an event/risk did not
exist** — every UNAVAILABLE entry says exactly why it is unavailable,
never a silently-assumed negative or zero (item 10's own instruction).
"""

from __future__ import annotations

import dataclasses
import json

from app.validation.enterprise_dataset_validation import (
    EnterpriseDatasetValidationReport,
)


def to_dict(report: EnterpriseDatasetValidationReport) -> dict:
    """The machine-readable form — a plain, JSON-serializable dict.
    Every field on the report is a plain dataclass/str/int/float/bool/
    list/dict already (no ORM row is ever embedded in this report), so
    `dataclasses.asdict()` alone is sufficient."""
    return dataclasses.asdict(report)


def to_json(report: EnterpriseDatasetValidationReport, *, indent: int = 2) -> str:
    return json.dumps(to_dict(report), indent=indent, default=str)


def _fmt_reasons(reasons: dict[str, int]) -> str:
    if not reasons:
        return "none"
    return ", ".join(f"{k}={v}" for k, v in reasons.items())


def to_markdown(report: EnterpriseDatasetValidationReport) -> str:
    o, i, q, t, term, pv, ir, pr = (
        report.observed, report.ingestion, report.data_quality, report.temporal,
        report.terminology_summary, report.provenance, report.intelligence_readiness, report.predictive_readiness,
    )
    lines = [
        "# Enterprise Dataset Validation Report",
        "",
        f"**{report.label}**",
        "",
        f"- Organization: `{report.organization_id}`",
        f"- Batch: `{report.batch_id}`",
        f"- Generated: {report.generated_at.isoformat()}",
        "",
        "## OBSERVED — what the dataset actually contains",
        "",
        f"- Total records: {o.total_records}",
        f"- Distinct source systems: {', '.join(o.distinct_source_systems) or 'none'}",
        f"- Distinct event_type terms (raw, unmapped): {o.distinct_event_type_terms}",
        (f"- Event time range: {o.earliest_event_time.isoformat() if o.earliest_event_time else 'n/a'} "
        f"to {o.latest_event_time.isoformat() if o.latest_event_time else 'n/a'}"),
        "",
        "## MAPPED — what SIE successfully normalized",
        "",
        f"- Valid: {i.valid} | Partial (usable, non-critical issue): {i.partial}",
        f"- Successfully processed (created or updated a canonical event): {i.successfully_processed}",
        f"- Terminology mapped, by domain: {term.mapped_by_domain or 'none'}",
        "",
        "## QUARANTINED — what SIE deliberately refused to interpret",
        "",
        f"- Quarantined records: {i.quarantined}",
        f"- Missing timestamps: {q.missing_timestamps} | Invalid classifications: {q.invalid_classifications}",
        (f"- Terminology requiring review: {term.review_required_total} of {term.unique_terms_total} unique terms "
        f"(unknown: {term.unknown_by_domain or 'none'}, ambiguous: {term.ambiguous_by_domain or 'none'})"),
        ("- These records are stored, but held out of every analytics/feature/signal "
        "calculation until reviewed — never silently trusted."),
        "",
        "## REJECTED — what failed ingestion outright",
        "",
        f"- Rejected (no canonical event): {i.rejected}",
        f"- Missing identifiers: {q.missing_identifiers}",
        f"- Duplicates (exact replay, no-op): {i.duplicates}",
        f"- Stale versions (late arrival, skipped): {i.stale_records}",
        f"- Version conflicts (same version, different content, refused): {i.version_conflicts}",
        "",
        "## UNAVAILABLE — what cannot be evaluated from this dataset",
        "",
        f"- Predictive labels not yet confirmable (horizon hasn't elapsed): {pr.unavailable_labels}",
        f"- Sites excluded from predictive readiness: {pr.excluded_sites} ({_fmt_reasons(pr.exclusion_reasons)})",
        f"- Missing feature values (summed across eligible sites): {pr.missing_features}",
        f"- Anomaly detection status: {ir.anomaly_status or 'not computed'}"
        + (" (insufficient baseline periods)" if ir.anomaly_status == "INSUFFICIENT_DATA" else ""),
        ("- Missing data is never interpreted as evidence an event/risk did not occur "
        "-- every entry above is reported as unavailable, not coerced into a zero or a negative."),
        "",
        "## Temporal integrity",
        "",
        f"- Out-of-order arrival detected: {t.out_of_order_arrival_detected}",
        f"- Duplicate timestamp groups: {t.duplicate_timestamp_groups}",
        f"- Future-dated records: {t.future_timestamp_records}",
        (f"- Corrections applied: {t.corrections_applied} | Stale versions skipped: {t.stale_versions_skipped} "
        f"| Version conflicts: {t.version_conflicts_detected}"),
        f"- Late-arriving records (ingested >24h after their own event_time): {t.late_arriving_records}",
        f"- Point-in-time leakage check passed: {t.as_of_leakage_check_passed}",
        "",
        f"> {t.retrospective_vs_point_in_time_note}",
        "",
        "## Provenance",
        "",
        f"- Chains checked: {pv.checked_count} | All intact: {pv.all_chains_intact}",
        f"- Failures: {pv.failures or 'none'}",
        f"- Feature/indicator stage reachable: {pv.feature_stage_reachable}",
        f"- Predictive-dataset stage reachable: {pv.predictive_stage_reachable}",
        "",
        "## Intelligence readiness",
        "",
        f"- Data sufficiency: {ir.data_sufficiency} (event_count={ir.event_count})",
        f"- Trend readiness: {ir.trend_readiness}",
        f"- Signals detected: {ir.signals_detected or 'none'}",
        "",
        "## Predictive dataset readiness",
        "",
        f"- Eligible sites: {pr.eligible_sites} | Excluded: {pr.excluded_sites}",
        f"- Qualifying incidents: {pr.qualifying_incidents}",
        (f"- Positive labels: {pr.positive_labels} | Negative labels: {pr.negative_labels} "
        f"| Unavailable labels: {pr.unavailable_labels}"),
        f"- Class distribution: {pr.class_distribution or 'not computed (no confirmed labels yet)'}",
        f"- Incomplete feature windows: {pr.incomplete_feature_windows}",
        ("- **No predictive accuracy, PR-AUC, ROC-AUC, precision, recall, or calibration performance is "
        "claimed anywhere in this report** -- this section measures dataset readiness for a future "
        "experiment only."),
        "",
    ]
    return "\n".join(lines)
