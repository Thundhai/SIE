# SIE Calibration Evaluation Report

**Prototype / controlled-scenario calibration only — not a production benchmark.**

Generated 2026-09-02T00:42:03.623285+00:00 by `tests/evaluation/test_calibration_evaluation.py`, running `tests/evaluation/calibration_harness.py::run_calibration_evaluation()` against real PostgreSQL. See that module's own docstring and `docs/CALIBRATION_METHODOLOGY.md` for what this is and is not: five controlled, synthetic, known-ground-truth scenarios exercising real, unmodified SIE ingestion/analytics/predictions code — never a production accuracy or performance claim, and never evidence this system behaves this way on a real customer's data.

## Scenario calibration results

| Scenario | Name | Records | Data quality (accepted/quarantined/rejected/duplicate) | Outcomes |
|---|---|---|---|---|
| A | Stable / Low Concern | 72 | 72/0/0/0 | near_miss_trend_stable=EXPECTED, incident_trend_stable=EXPECTED, no_risk_signals=EXPECTED |
| B | Emerging Risk | 77 | 77/0/0/0 | near_miss_trend_increasing=EXPECTED, unsafe_observation_surge_fires=EXPECTED, training_compliance_drop_fires=EXPECTED, no_lagging_signal_from_leading_only_data=EXPECTED |
| C | Lagging Event Increase | 65 | 65/0/0/0 | incident_trend_increasing=EXPECTED, near_miss_trend_stable=EXPECTED, high_potential_event_cluster_fires=EXPECTED, anomaly_detected_where_statistically_justified=EXPECTED |
| D | Data Quality Degradation | 16 | 10/2/2/1 | quality_degradation_reflected_in_metrics=EXPECTED, quarantined_records_excluded_from_analytics=EXPECTED, version_conflict_detected_not_silently_applied=EXPECTED |
| E | Recovery | 53 | 53/0/0/0 | near_miss_trend_decreasing=EXPECTED, training_completion_recovered=EXPECTED, no_training_compliance_drop_in_recovered_window=EXPECTED |

### Expected vs. actual intelligence, per scenario

**Scenario A — Stable / Low Concern**

- Description: Flat incident frequency, good inspection coverage, low repeat findings, ~90% training completion, low maintenance backlog across four consecutive 30-day periods.
- Expected: `{'near_miss_trend': 'STABLE', 'incident_trend': 'STABLE', 'risk_signals': 'none'}`
- Actual: `{'near_miss_trend': 'STABLE', 'incident_trend': 'STABLE', 'risk_signals': 'none'}`

**Scenario B — Emerging Risk**

- Description: Sharp increase in near misses, unsafe observations, overdue training, overdue maintenance, and repeat findings in the most recent 30 days against a quiet 90-day baseline; incident frequency itself stays flat -- leading indicators only, no claimed causation.
- Expected: `{'near_miss_trend': 'INCREASING', 'unsafe_observation_surge': 'fires', 'training_compliance_drop': 'fires', 'high_potential_event_cluster': 'does not fire'}`
- Actual: `{'near_miss_trend': 'INCREASING', 'risk_signals': ['TRAINING_COMPLIANCE_DROP', 'UNSAFE_OBSERVATION_SURGE']}`
- Note: Leading-indicator deterioration only -- no claim that these factors caused an incident.

**Scenario C — Lagging Event Increase**

- Description: Leading indicators stay identical to a stable four-period baseline; a sudden cluster of six high-potential incidents appears only in the current 30-day window.
- Expected: `{'incident_trend': 'INCREASING', 'near_miss_trend': 'STABLE', 'high_potential_event_cluster': 'fires', 'anomaly': 'ANOMALOUS'}`
- Actual: `{'incident_trend': 'INCREASING', 'near_miss_trend': 'STABLE', 'risk_signals': ['HIGH_POTENTIAL_EVENT_CLUSTER'], 'anomaly_status': 'ANOMALOUS', 'anomaly_baseline_counts': [1, 1, 1, 1], 'anomaly_current_count': 6}`

**Scenario D — Data Quality Degradation**

- Description: Missing event dates, an invalid severity classification, an exact-duplicate resend, a same-version content conflict, and records missing their identifier, deliberately mixed with genuinely valid records.
- Expected: `{'quarantined_records': '> 0', 'rejected_records': '> 0', 'duplicate_records': '> 0', 'version_conflicts': '> 0', 'analytics_event_count': '== accepted (VALID+PARTIAL) records only'}`
- Actual: `{'quarantined_records': 2, 'rejected_records': 2, 'duplicate_records': 1, 'version_conflicts': 1, 'analytics_event_count': 10}`
- Note: Schema validity only -- never presented as factual correctness of the underlying record.

**Scenario E — Recovery**

- Description: An elevated period 60-90 days ago (frequent near misses, overdue training, high maintenance backlog, repeat findings) improving through a transitional period into a recovered most-recent 30 days.
- Expected: `{'near_miss_trend': 'DECREASING', 'training_completion_rate': '>= 0.8', 'training_compliance_drop': 'does not fire'}`
- Actual: `{'near_miss_trend': 'DECREASING', 'training_completion_rate': 0.8889, 'risk_signals': 'none'}`
- Note: Indicators moving in the improving direction is not, by itself, proof of actual safety improvement -- see this module's own docstring and the milestone's own caution.

## Provenance validation (item 7)

- Records checked: 72
- All chains intact: True
- Failures: none

## Predictive dataset readiness (item 10)

Construction correctness only — no claim of predictive model accuracy.

- Examples built: 3
- Reproducible: True
- No future leakage: True
- Tenant isolated: True
- Missing-data handled: True

## Multi-tenant isolation (item 12)

- Org A events visible to org B: 0
- Org B events visible to org A: 0
- Quality metrics isolated: True
- Predictive dataset isolated: True

## Limitations

- Five controlled, synthetic scenarios with known ground truth — not real
  customer data, not a statistically representative sample, not a claim about
  any specific organization's future safety outcomes.
- Calibration outcomes are EXPECTED/UNEXPECTED/INDETERMINATE against each
  scenario's own designed direction, not a accuracy/precision/recall metric
  against real-world ground truth (there is none to measure against yet).
- Anomaly and signal thresholds are this codebase's existing, unmodified
  configuration (`INTELLIGENCE_*` settings) — calibration here confirms they
  fire/don't fire as designed on these scenarios, not that the thresholds
  themselves are the right ones for any particular real deployment.
