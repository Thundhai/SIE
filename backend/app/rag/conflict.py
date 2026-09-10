"""Source conflict detection — milestone items 15/36. A small, explicit,
deterministic rule set — **not** a machine-learning classifier and not
claimed to be a general-purpose contradiction detector (see the "Known
limitations" section this module's docstring points to in the README).
It exists to catch the one concrete shape the milestone's own example
describes: two evidence items making the *same* kind of requirement
statement about the *same* subject, where one asserts it and the other
negates it — e.g. "Hard hats are required." vs. "Hard hats are not
required."

**The rule:** for every pair of selected evidence items that each contain
a requirement cue word (a set like "required"/"must"/"mandatory"), compute
the Jaccard overlap of their *topic tokens* — content words with
stopwords, requirement cues, and negation cues all removed, i.e. what the
statement is actually *about*. If that overlap clears
`RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD` (same subject) **and** exactly one
of the two contains a negation cue ("not"/"no"/"never"/"without"/...)
while the other does not (opposite polarity), the pair is flagged.

**What this deliberately does not do:** it never resolves a detected
conflict, never picks a "winning" source, and never claims to catch every
real-world contradiction (paraphrased conflicts with no shared vocabulary,
or ones that don't hinge on an explicit negation word, will not be
detected — this is a defense-in-depth heuristic, not a guarantee; see the
README's "Prompt security"/"Known limitations" sections for the identical
honesty standard already applied to prompt-injection defense). When a
conflict *is* flagged, `RAGService` never asks the LLM to adjudicate it —
see that module's docstring.
"""

from __future__ import annotations

import re

from app.core.config import settings
from app.rag.results import SelectedEvidenceItem, SourceConflict

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    """
    a an the this that these those is are was were be been being
    of to in on at for with by from as into over under
    and or but if then than so
    it its their there here
    do does did done
    all any some each every
    before after when where while during
    """.split()  # noqa: SIM905
)

_REQUIREMENT_CUES = frozenset(
    {"required", "require", "requires", "mandatory", "must", "shall", "necessary", "needed"}
)

_NEGATION_CUES = frozenset({"not", "no", "never", "without", "prohibited", "excluded", "unnecessary"})


def _significant_tokens(text: str) -> frozenset[str]:
    words = _WORD_RE.findall(text.lower())
    return frozenset(
        w for w in words if w not in _STOPWORDS and w not in _REQUIREMENT_CUES and w not in _NEGATION_CUES
    )


def _has_any(text_tokens: list[str], cues: frozenset[str]) -> bool:
    return any(token in cues for token in text_tokens)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_conflicts(
    selected: list[SelectedEvidenceItem],
    *,
    topic_overlap_threshold: float | None = None,
) -> list[SourceConflict]:
    threshold = (
        topic_overlap_threshold
        if topic_overlap_threshold is not None
        else settings.RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD
    )

    # Only candidates that make an explicit requirement-type statement —
    # conflict detection is deliberately narrow, not a general semantic
    # contradiction check (see module docstring).
    candidates = []
    for item in selected:
        words = _WORD_RE.findall(item.result.content.lower())
        if _has_any(words, _REQUIREMENT_CUES):
            candidates.append((item, words, _significant_tokens(item.result.content)))

    conflicts: list[SourceConflict] = []
    for i in range(len(candidates)):
        item_a, words_a, topic_a = candidates[i]
        for j in range(i + 1, len(candidates)):
            item_b, words_b, topic_b = candidates[j]

            negated_a = _has_any(words_a, _NEGATION_CUES)
            negated_b = _has_any(words_b, _NEGATION_CUES)
            if negated_a == negated_b:
                continue  # same polarity -> not a conflict by this rule

            if _jaccard(topic_a, topic_b) < threshold:
                continue  # not plausibly about the same subject

            conflicts.append(
                SourceConflict(
                    citation_id_a=item_a.citation_id,
                    citation_id_b=item_b.citation_id,
                    statement_a=item_a.result.content,
                    statement_b=item_b.result.content,
                    source_name_a=item_a.result.source_name,
                    source_name_b=item_b.result.source_name,
                    version_label_a=item_a.result.version_label,
                    version_label_b=item_b.result.version_label,
                    effective_date_a=item_a.result.effective_date,
                    effective_date_b=item_b.result.effective_date,
                )
            )

    return conflicts
