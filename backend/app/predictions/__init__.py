"""Predictive Risk Modeling — SIE Predictive Risk Modeling Specification
v0.1.

See `app/predictions/spec.py` for the full specification every other
module here implements, and the "Predictive Intelligence Architecture"
section of the top-level README for the end-to-end pipeline this package
provides: deterministic label generation (`labels.py`), versioned/
persisted feature snapshots (`feature_snapshot_service.py`), training-
example construction (`dataset.py`), chronological splitting
(`temporal_split.py`) and walk-forward backtesting (`walk_forward.py`), a
hand-rolled logistic regression baseline (`logistic_regression.py`),
Recall/Precision/PR-AUC-first evaluation (`metrics.py`), a minimal model
registry with an enforced human-review lifecycle (`model_registry.py`),
training orchestration (`training.py`), abstention-aware prediction
serving (`predictor.py`), and coefficient-based, non-causal explanations
(`explain.py`).

**Only a prototype baseline model, trained on synthetic data, is ever
produced by this package** (`training.py::PROTOTYPE_MODEL_LABEL`) — see
`spec.py` and the README for the full, explicit scope boundary.
"""
