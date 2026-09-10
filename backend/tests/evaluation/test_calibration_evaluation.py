"""Real-World Data Validation & Intelligence Calibration v0.1 — pytest
wrapper around `tests/evaluation/calibration_harness.py`'s
`run_calibration_evaluation()`.

**Requires real PostgreSQL** (`@requires_postgres`, `pg_session` —
skipped, not failed, where no server is reachable; see
`tests/postgres_support.py`). The harness's own no-future-leakage check
(item 5/10) compares raw Python `datetime` values against stored
`event_time`; SQLite has no native timezone-aware datetime type and
either raises `TypeError: can't compare offset-naive and offset-aware
datetimes` or silently mis-orders the comparison, depending on the
query. This mirrors this suite's own existing precedent (see
`tests/test_performance_baseline.py`'s retrieval/RAG baseline, and every
`@requires_postgres` test in this repository) of routing anything that
genuinely depends on real temporal or vector correctness through
Postgres rather than faking it against SQLite.

Writes both `docs/CALIBRATION_EVALUATION_REPORT.md` (human-readable) and
`docs/CALIBRATION_EVALUATION_REPORT.json` (machine-readable) — item 14 —
each stamped with `calibration_harness.REPORT_LABEL`: *"Prototype /
controlled-scenario calibration only — not a production benchmark."*
Neither file, nor any assertion below, is evidence of production
accuracy — see the harness module's own docstring and this milestone's
own governing caution against overclaiming from controlled synthetic
scenarios.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from tests.evaluation.calibration_harness import (
    REPORT_LABEL,
    CalibrationEvaluationReport,
    run_calibration_evaluation,
)
from tests.postgres_support import requires_postgres

REPORT_MD_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "CALIBRATION_EVALUATION_REPORT.md"
REPORT_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "CALIBRATION_EVALUATION_REPORT.json"

# Populated by test_calibration_evaluation_runs_and_calibrates_as_expected
# below and consumed by test_zzz_write_calibration_report, mirroring
# tests/test_performance_baseline.py's own module-level `_results` +
# "zzz"-ordered final report-writing test pattern -- one real evaluation
# run, asserted against and then reported on, never two separate runs
# that could disagree.
_report: CalibrationEvaluationReport | None = None

# Deterministic, seed-derived record counts (tests/fixtures/enterprise_scenarios.py's
# own default seeds 1001-1005) -- item 11/13's reproducibility requirement,
# checked directly rather than merely hoped for.
_EXPECTED_RECORD_COUNTS = {"A": 72, "B": 77, "C": 65, "D": 16, "E": 53}


@requires_postgres
def test_calibration_evaluation_runs_and_calibrates_as_expected(pg_session):
    global _report
    report = run_calibration_evaluation(pg_session)
    _report = report

    # --- Item 11/13: realistic volume, deterministic and reproducible -------------------
    for key, expected_count in _EXPECTED_RECORD_COUNTS.items():
        assert report.scenarios[key].dataset_record_count == expected_count

    # --- Item 8/9: calibration outcomes -- every controlled scenario's own known-correct
    # direction must actually be recovered from real ingestion + real, unchanged
    # analytics/signals/anomaly code, not merely fail to error. `all_expected()`
    # is strict (every calibration_outcomes entry == EXPECTED); scenarios are
    # deliberately designed so a correct implementation clears this bar --
    # an UNEXPECTED or INDETERMINATE result here is a real calibration finding,
    # not something to loosen the assertion around.
    for key in _EXPECTED_RECORD_COUNTS:
        result = report.scenarios[key]
        assert result.all_expected(), (
            f"Scenario {key} ({result.scenario_name}) did not calibrate as expected: "
            f"{result.calibration_outcomes} -- actual: {result.actual_intelligence}"
        )

    # --- Item 7: provenance chain intact for every accepted canonical event -------------
    assert report.provenance.checked_count > 0
    assert report.provenance.all_chains_intact
    assert report.provenance.failures == []

    # --- Item 10: predictive dataset readiness -- construction correctness, not model
    # quality; no claim of predictive accuracy anywhere in this assertion.
    assert report.predictive_readiness.examples_built > 0
    assert report.predictive_readiness.reproducible
    assert report.predictive_readiness.no_future_leakage
    assert report.predictive_readiness.tenant_isolated
    assert report.predictive_readiness.missing_data_handled

    # --- Item 12: multi-tenant isolation ------------------------------------------------
    assert report.tenant_isolation.org_a_events_visible_to_org_b == 0
    assert report.tenant_isolation.org_b_events_visible_to_org_a == 0
    assert report.tenant_isolation.quality_metrics_isolated
    assert report.tenant_isolation.predictive_dataset_isolated

    print(f"\n[calibration] {REPORT_LABEL}")
    for key, result in report.scenarios.items():
        print(f"[calibration] {key} {result.scenario_name}: {result.calibration_outcomes}")


def _write_json_report(report: CalibrationEvaluationReport) -> None:
    payload = dataclasses.asdict(report)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    REPORT_JSON_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _write_markdown_report(report: CalibrationEvaluationReport) -> None:
    lines = [
        "# SIE Calibration Evaluation Report",
        "",
        f"**{REPORT_LABEL}**",
        "",
        (
            f"Generated {datetime.now(timezone.utc).isoformat()} by "
            "`tests/evaluation/test_calibration_evaluation.py`, running "
            "`tests/evaluation/calibration_harness.py::run_calibration_evaluation()` "
            "against real PostgreSQL. See that module's own docstring and "
            "`docs/CALIBRATION_METHODOLOGY.md` for what this is and is not: five "
            "controlled, synthetic, known-ground-truth scenarios exercising real, "
            "unmodified SIE ingestion/analytics/predictions code — never a "
            "production accuracy or performance claim, and never evidence this "
            "system behaves this way on a real customer's data."
        ),
        "",
        "## Scenario calibration results",
        "",
        "| Scenario | Name | Records | Data quality (accepted/quarantined/rejected/duplicate) | Outcomes |",
        "|---|---|---|---|---|",
    ]
    for key, result in report.scenarios.items():
        dq = result.data_quality
        outcomes = ", ".join(f"{k}={v}" for k, v in result.calibration_outcomes.items())
        lines.append(
            f"| {key} | {result.scenario_name} | {result.dataset_record_count} | "
            f"{dq.valid_records}/{dq.quarantined_records}/{dq.rejected_records}/{dq.duplicate_records} | "
            f"{outcomes} |"
        )

    lines += ["", "### Expected vs. actual intelligence, per scenario", ""]
    for key, result in report.scenarios.items():
        lines.append(f"**Scenario {key} — {result.scenario_name}**")
        lines.append("")
        lines.append(f"- Description: {result.description}")
        lines.append(f"- Expected: `{result.expected_intelligence}`")
        lines.append(f"- Actual: `{result.actual_intelligence}`")
        if result.notes:
            for note in result.notes:
                lines.append(f"- Note: {note}")
        lines.append("")

    lines += [
        "## Provenance validation (item 7)",
        "",
        f"- Records checked: {report.provenance.checked_count}",
        f"- All chains intact: {report.provenance.all_chains_intact}",
        f"- Failures: {report.provenance.failures or 'none'}",
        "",
        "## Predictive dataset readiness (item 10)",
        "",
        "Construction correctness only — no claim of predictive model accuracy.",
        "",
        f"- Examples built: {report.predictive_readiness.examples_built}",
        f"- Reproducible: {report.predictive_readiness.reproducible}",
        f"- No future leakage: {report.predictive_readiness.no_future_leakage}",
        f"- Tenant isolated: {report.predictive_readiness.tenant_isolated}",
        f"- Missing-data handled: {report.predictive_readiness.missing_data_handled}",
        "",
        "## Multi-tenant isolation (item 12)",
        "",
        f"- Org A events visible to org B: {report.tenant_isolation.org_a_events_visible_to_org_b}",
        f"- Org B events visible to org A: {report.tenant_isolation.org_b_events_visible_to_org_a}",
        f"- Quality metrics isolated: {report.tenant_isolation.quality_metrics_isolated}",
        f"- Predictive dataset isolated: {report.tenant_isolation.predictive_dataset_isolated}",
        "",
        "## Limitations",
        "",
        "- Five controlled, synthetic scenarios with known ground truth — not real",
        "  customer data, not a statistically representative sample, not a claim about",
        "  any specific organization's future safety outcomes.",
        "- Calibration outcomes are EXPECTED/UNEXPECTED/INDETERMINATE against each",
        "  scenario's own designed direction, not a accuracy/precision/recall metric",
        "  against real-world ground truth (there is none to measure against yet).",
        "- Anomaly and signal thresholds are this codebase's existing, unmodified",
        "  configuration (`INTELLIGENCE_*` settings) — calibration here confirms they",
        "  fire/don't fire as designed on these scenarios, not that the thresholds",
        "  themselves are the right ones for any particular real deployment.",
        "",
    ]
    REPORT_MD_PATH.write_text("\n".join(lines))


def test_zzz_write_calibration_report():
    assert _report is not None, "run_calibration_evaluation() must run before the report can be written"
    _write_json_report(_report)
    _write_markdown_report(_report)
