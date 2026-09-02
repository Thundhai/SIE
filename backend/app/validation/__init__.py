"""Real Enterprise Dataset Validation Foundation v0.1 — a reusable
harness for evaluating whether a real (later, anonymized-customer)
enterprise dataset can be safely ingested, validated, normalized, and
whether SIE's existing intelligence/predictive pipelines have enough
trustworthy data to operate on it.

Production code, not test-only: unlike
`tests/evaluation/calibration_harness.py` (Real-World Data Validation &
Intelligence Calibration v0.1's own controlled-scenario calibration
exercise), this package is meant to be run again, later, against a real
dataset once one is supplied — see `app/validation/enterprise_dataset_validation.py`'s
own module docstring for the full design and
`docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md` for how to use it.
"""
