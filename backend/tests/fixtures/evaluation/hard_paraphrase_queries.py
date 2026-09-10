"""Hard semantic-paraphrase evaluation queries — SIE Milestone 21: Real
Semantic Embedding & Retrieval Productionization v0.1, item 11.

Distinct from `tests/fixtures/evaluation/queries.py` (that file's queries
already avoid copying corpus text verbatim, but several still share
obvious domain vocabulary with their correct chunk — "confined space",
"harness", "permit to work" — which a purely lexical/keyword-overlap
method can exploit). This file's queries are written to *additionally*
minimize shared surface vocabulary with the corpus chunk they're meant to
match, so that a method with no real semantic understanding (the
deterministic hashing provider — see app/embeddings/provider.py) has
little to no lexical signal to work with, while the underlying meaning
still clearly points at one topic in
`tests/fixtures/evaluation/corpus.py`.

Not copied from, and not the same sentences as,
`tests/fixtures/evaluation/semantic_training_pairs.py` — that file is
what a locally-trained real model (see `scripts/train_local_semantic_model.py`)
is trained *on*; this file is what it is *evaluated against*. Training on
the exact evaluation set would make any recall measured here memorization,
not generalization, and this milestone is explicit that a real evaluation
result must not be manufactured that way.

Two queries per topic, matching `tests/fixtures/evaluation/corpus.py`'s
six topics exactly, in the same `EvaluationQuery` shape
`tests/evaluation/harness.py::run_recall_at_k` already consumes — so this
file is a drop-in alternative query set for that same, unmodified harness
(via its own `queries=` parameter), not a new evaluation mechanism.
"""

from tests.fixtures.evaluation.queries import EvaluationQuery

HARD_PARAPHRASE_QUERIES: list[EvaluationQuery] = [
    EvaluationQuery(
        "What stops someone from hitting the ground if they slip off a ladder or scaffold?",
        "working_at_height",
    ),
    EvaluationQuery(
        "Should people keep working up on a platform if it's storming outside?",
        "working_at_height",
    ),
    EvaluationQuery(
        "Why shouldn't anyone walk underneath something a crane is moving?",
        "lifting_operations",
    ),
    EvaluationQuery(
        "What paperwork needs to exist before a heavy object gets hoisted with machinery?",
        "lifting_operations",
    ),
    EvaluationQuery(
        "Does someone need sign-off before starting a dangerous task like welding?",
        "permit_to_work",
    ),
    EvaluationQuery(
        "What happens to the paperwork once a risky job is finished?",
        "permit_to_work",
    ),
    EvaluationQuery(
        "What breathing gear do I need if the air quality on site is bad?",
        "ppe",
    ),
    EvaluationQuery(
        "What should I put on my feet and head before walking into an active work zone?",
        "ppe",
    ),
    EvaluationQuery(
        "Does someone need to watch the entrance while a colleague is inside a tank?",
        "confined_spaces",
    ),
    EvaluationQuery(
        "What needs to happen to the air quality before someone climbs into an enclosed tank?",
        "confined_spaces",
    ),
    EvaluationQuery(
        "What should I do if I don't know what liquid leaked out of a drum?",
        "emergency_response",
    ),
    EvaluationQuery(
        "How does a site make sure nobody got left behind after everyone runs outside?",
        "emergency_response",
    ),
]
