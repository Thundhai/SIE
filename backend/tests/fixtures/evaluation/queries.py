"""Evaluation query set for the Recall@K harness — milestone spec item 19.

Two queries per topic in tests/fixtures/evaluation/corpus.py, phrased the
way a person would actually ask (not copied verbatim from any corpus
chunk), including the milestone's own three worked examples. Synthetic,
non-confidential.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationQuery:
    query: str
    expected_topic: str


QUERIES: list[EvaluationQuery] = [
    EvaluationQuery("What controls are required for working at height?", "working_at_height"),
    EvaluationQuery(
        "What fall protection equipment must workers wear above 1.8 metres?",
        "working_at_height",
    ),
    EvaluationQuery(
        "What checks should be completed before a lifting operation?", "lifting_operations"
    ),
    EvaluationQuery(
        "Who is allowed to operate a crane during a lift?", "lifting_operations"
    ),
    EvaluationQuery("When is a permit to work needed?", "permit_to_work"),
    EvaluationQuery(
        "What happens when a permit to work is finished?", "permit_to_work"
    ),
    EvaluationQuery("What personal protective equipment is required on site?", "ppe"),
    EvaluationQuery("What respiratory protection is needed for airborne contaminants?", "ppe"),
    EvaluationQuery("What is required before entering a confined space?", "confined_spaces"),
    EvaluationQuery(
        "Who needs to stay outside while someone works in a confined space?",
        "confined_spaces",
    ),
    EvaluationQuery("What should I do if there is a fire alarm?", "emergency_response"),
    EvaluationQuery(
        "How is a chemical spill handled in an emergency?", "emergency_response"
    ),
]
