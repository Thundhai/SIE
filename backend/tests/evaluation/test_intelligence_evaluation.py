"""Intelligence evaluation harness test — milestone item 41. Runs
against the ordinary SQLite `db_session` fixture — nothing here needs
pgvector. See tests/evaluation/intelligence_harness.py's own docstring
for what this is and is not: a small, synthetic, regression-catching
check, never a production/enterprise accuracy claim.
"""

from app.intelligence.enums import DataSufficiency, TrendDirection
from tests.evaluation.intelligence_harness import seed_and_evaluate


def test_intelligence_evaluation_runs_and_reports_measured_results(db_session):
    report = seed_and_evaluate(db_session)
    print(report.summary())  # surfaced in `pytest -s` output / CI logs, not fabricated

    # --- Data quality (milestone item 41) -----------------------------------------------
    malformed = report.ingestion_results["malformed_records_org"]
    assert malformed["created"] == 3  # quarantined + partial + valid, all still stored
    assert malformed["rejected"] == 1  # missing source_record_id

    duplicate = report.ingestion_results["duplicate_records_org"]
    assert duplicate["created"] == 1
    assert duplicate["duplicate_in_batch"] == 1  # the resend, not a second row

    # --- Trend correctness ----------------------------------------------------------------
    assert report.trend_direction == TrendDirection.INCREASING.value

    # --- Signal detection: correct positives, and no false positive on sparse data --------
    assert "HIGH_POTENTIAL_EVENT_CLUSTER" in report.trending_org_signal_types or (
        "EQUIPMENT_FAILURE_CLUSTER" in report.trending_org_signal_types
    )
    assert "TRAINING_COMPLIANCE_DROP" in report.trending_org_signal_types
    assert report.sparse_org_signal_count == 0  # milestone item 53

    # --- Insufficient-data behavior ---------------------------------------------------------
    assert report.sufficiency_by_org["sparse_data_org"] in (
        DataSufficiency.INSUFFICIENT_DATA.value, DataSufficiency.LIMITED_DATA.value,
    )
    assert report.sufficiency_by_org["trending_org"] == DataSufficiency.SUFFICIENT_DATA.value

    # --- Data freshness ----------------------------------------------------------------------
    assert report.stale_org_is_stale is True
    assert report.fresh_org_is_stale is False

    # --- Exposure normalization ----------------------------------------------------------------
    assert report.missing_exposure_unavailable_reason == "EXPOSURE_DATA_UNAVAILABLE"
    assert report.trending_org_exposure_rate is not None
    assert isinstance(report.trending_org_exposure_rate, float)

    # --- Temporal integrity (milestone item 16/50) -----------------------------------------
    assert report.temporal_leakage_detected is False

    # --- Tenant security (milestone item 36/41) --------------------------------------------
    assert report.cross_tenant_leakage_count == 0
