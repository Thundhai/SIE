"""False negative / false positive error analysis — Model Validation &
Governance v0.1, items 12-13.

**"What kinds of situations is the model missing?" matters more than the
aggregate score (item 12's own framing).** `analyze_errors()` returns
every individual false negative and false positive as a full,
inspectable record — entity, `as_of`, the exact feature vector and data
quality the model saw, the supporting events behind the label, and which
model version produced the score — not just a count. A reviewer reading
this output can go look at the actual site and actual events behind each
miss, the same provenance chain `app/predictions/predictor.py` gives a
live prediction.

**No false positive is auto-classified as "useless" (item 13).** This
module only surfaces the record; `notes`/triage is left to the human
review that milestone item 13 asks for — a "false" positive can be a
legitimate early warning, a data-quality artifact, an unusual (but real)
operational change, or a genuine model error, and nothing here decides
which.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.predictions.dataset import TrainingExample
from app.predictions.threshold import DEFAULT_DECISION_THRESHOLD


@dataclass
class ErrorRecord:
    entity_type: str
    entity_id: uuid.UUID
    as_of: datetime
    predicted_label: int
    actual_label: int
    risk_score: float
    data_quality: str
    feature_vector: dict
    feature_snapshot_id: uuid.UUID
    supporting_event_ids: list
    model_version: str


@dataclass
class ErrorAnalysisReport:
    false_negatives: list[ErrorRecord]
    false_positives: list[ErrorRecord]
    threshold: float

    @property
    def false_negative_count(self) -> int:
        return len(self.false_negatives)

    @property
    def false_positive_count(self) -> int:
        return len(self.false_positives)


def analyze_errors(
    examples: list[TrainingExample],
    scores: list[float],
    *,
    model_version: str,
    threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> ErrorAnalysisReport:
    if len(examples) != len(scores):
        raise ValueError("examples and scores must have the same length.")

    false_negatives: list[ErrorRecord] = []
    false_positives: list[ErrorRecord] = []

    for example, score in zip(examples, scores):
        predicted_label = 1 if score >= threshold else 0
        if predicted_label == example.label:
            continue

        record = ErrorRecord(
            entity_type=example.entity_type,
            entity_id=example.entity_id,
            as_of=example.as_of,
            predicted_label=predicted_label,
            actual_label=example.label,
            risk_score=score,
            data_quality=example.data_quality,
            feature_vector=dict(example.feature_vector),
            feature_snapshot_id=example.feature_snapshot_id,
            supporting_event_ids=list(example.supporting_event_ids),
            model_version=model_version,
        )
        if predicted_label == 0 and example.label == 1:
            false_negatives.append(record)
        else:
            false_positives.append(record)

    return ErrorAnalysisReport(false_negatives=false_negatives, false_positives=false_positives, threshold=threshold)


__all__ = ["ErrorAnalysisReport", "ErrorRecord", "analyze_errors"]
