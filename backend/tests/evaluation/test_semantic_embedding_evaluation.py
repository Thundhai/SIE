"""SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization
v0.1, item 11 — the hashing-vs-real semantic embedding evaluation.

**Requires real PostgreSQL** (`@requires_postgres` — see
`tests/postgres_support.py`) for the same reason
`tests/evaluation/test_recall_at_k.py` does: real pgvector cosine-distance
operators.

Always runs the hashing (deterministic baseline) side — it has no
external dependency and is the same regression check
`test_recall_at_k.py` already performs, just also captured into this
milestone's own report. The real-provider side runs **only** when
`scripts/train_local_semantic_model.py` has already been run in this
checkout (its output directory is untracked by Git — see
`backend/.gitignore`) — this test never fails, and never silently
fabricates results, when that model is absent; it records
`real_provider_available: false` in the report instead. This is the
"CI deterministic regression + separate real-model validation" split
item 17 asks for: CI's own `pytest -q` run always has the hashing
comparison available, never the real-model one (nothing in this
repository commits or downloads that model), so CI itself only ever
exercises the baseline half of this test — the real-model half is a
local, on-demand validation step, honestly labeled as such wherever its
results are reported.

Writes `docs/SEMANTIC_EVALUATION_REPORT.md` (human-readable) and
`docs/SEMANTIC_EVALUATION_REPORT.json` (machine-readable), mirroring
`tests/evaluation/test_calibration_evaluation.py`'s own report-writing
pattern. Neither file is evidence of production semantic quality — see
`RESULT_LABEL_HASHING`/`RESULT_LABEL_REAL` in
`tests/evaluation/semantic_evaluation_harness.py`, reproduced verbatim in
both report files.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from tests.evaluation.semantic_evaluation_harness import (
    RESULT_LABEL_HASHING,
    RESULT_LABEL_REAL,
    SemanticEvaluationReport,
    run_semantic_evaluation,
)
from tests.postgres_support import requires_postgres

REPORT_MD_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "SEMANTIC_EVALUATION_REPORT.md"
REPORT_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "SEMANTIC_EVALUATION_REPORT.json"

# Populated by test_semantic_evaluation_runs below, consumed by
# test_zzz_write_semantic_evaluation_report -- one real evaluation run,
# asserted against and then reported on (see
# tests/evaluation/test_calibration_evaluation.py's own identical
# pattern and rationale).
_report: SemanticEvaluationReport | None = None


@requires_postgres
def test_semantic_evaluation_runs(pg_session, capsys):
    global _report
    report = run_semantic_evaluation(pg_session)
    _report = report

    for result in report.results:
        # The one loose, regression-catching bar this suite has always
        # asserted (see test_recall_at_k.py's own identical floor and
        # rationale) -- exists to catch retrieval breaking outright, not
        # to pin an exact score. Only applied to the existing, lighter
        # query set: the deliberately harder, keyword-disjoint set is
        # *expected* to be difficult for a bag-of-words method and is not
        # held to the same floor -- asserting a hashing-provider bar on
        # queries specifically designed to defeat hashing would be the
        # "manufactured threshold" this milestone explicitly warns against.
        if result.query_set_name == "existing_paraphrase_queries":
            assert result.hashing.recall_at_k[5] >= 0.5, (
                f"Recall@5 dropped below the regression floor on "
                f"{result.query_set_name}: {result.hashing.summary()}"
            )

        # Recall@K is monotonically non-decreasing in K by construction,
        # for both providers -- a real mathematical invariant, not a
        # quality claim.
        assert result.hashing.recall_at_k[1] <= result.hashing.recall_at_k[3] <= result.hashing.recall_at_k[5]
        if result.real is not None:
            assert result.real.recall_at_k[1] <= result.real.recall_at_k[3] <= result.real.recall_at_k[5]

    print(f"\n[semantic-eval] real_provider_available={report.real_provider_available}")
    for result in report.results:
        print(f"[semantic-eval] {result.query_set_name}")
        print(f"  hashing: {result.hashing.summary()}")
        if result.real is not None:
            print(f"  real:    {result.real.summary()}")
        else:
            print("  real:    (skipped -- run scripts/train_local_semantic_model.py first)")


def _write_json_report(report: SemanticEvaluationReport) -> None:
    payload = dataclasses.asdict(report)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["hashing_label"] = RESULT_LABEL_HASHING
    payload["real_label"] = RESULT_LABEL_REAL
    REPORT_JSON_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _format_recall(report) -> str:
    return ", ".join(f"Recall@{k}={report.recall_at_k[k]:.2f}" for k in report.ks)


def _write_markdown_report(report: SemanticEvaluationReport) -> None:
    lines = [
        "# SIE Semantic Embedding Evaluation Report",
        "",
        "**SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization v0.1.**",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()} by "
        "`tests/evaluation/test_semantic_embedding_evaluation.py` against a real "
        "PostgreSQL 16 + pgvector database.",
        "",
        "## What this is, and is not",
        "",
        f"- **Hashing baseline:** {RESULT_LABEL_HASHING}",
        f"- **Real semantic embedding:** {RESULT_LABEL_REAL}",
        "",
        "This is a small, synthetic-fixture evaluation (28 corpus chunks across 6 "
        "safety topics) — a regression/sanity check and an honest, real comparison "
        "between the two provider implementations this codebase actually ships, "
        "**not** a production accuracy benchmark, and **not** a claim about the "
        "recommended production pretrained model's quality (this environment could "
        "not download it — see docs/SEMANTIC_EMBEDDING.md).",
        "",
        f"**Real-model validation performed in this run:** "
        f"{'yes' if report.real_provider_available else 'no (scripts/train_local_semantic_model.py had not been run)'}",
    ]

    if report.real_provider_available:
        lines += [
            f"**Real model:** `{report.real_provider_model_name}` "
            f"({report.real_provider_dimensions} dimensions)",
        ]

    lines += ["", "## Results", ""]

    for result in report.results:
        lines.append(f"### {result.query_set_name}")
        lines.append("")
        lines.append(f"- Hashing: {_format_recall(result.hashing)} (n={len(result.hashing.per_query)} queries)")
        if result.real is not None:
            lines.append(f"- Real:    {_format_recall(result.real)} (n={len(result.real.per_query)} queries)")
        else:
            lines.append("- Real:    (skipped in this run)")
        lines.append("")

    lines += ["## Performance benchmark", "", "Baseline only — not a production SLA. One `embed_texts()` call over the 28-chunk corpus, timed end to end.", ""]
    lines.append("| Provider | Model | Texts | Batch size | Dimensions | Total (s) | Avg latency (ms) | Throughput (texts/s) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for bench in report.benchmarks:
        lines.append(
            f"| {bench.provider_name} | {bench.model_name} | {bench.num_texts} | "
            f"{bench.batch_size} | {bench.dimensions} | {bench.total_seconds} | "
            f"{bench.avg_latency_ms} | {bench.throughput_texts_per_second} |"
        )
    lines.append("")

    lines += [
        "## Methodology",
        "",
        "- Corpus: `tests/fixtures/evaluation/corpus.py` — 28 synthetic, "
        "non-confidential safety-domain chunks across 6 topics, seeded once per "
        "provider (each provider embeds its own independent copy of the corpus, "
        "isolated by the existing model-identity filter — see "
        "`app/retrieval/retrieval_service.py::_model_clause`).",
        "- Query sets:",
        "  - `existing_paraphrase_queries` — "
        "`tests/fixtures/evaluation/queries.py`, 12 queries.",
        "  - `hard_keyword_disjoint_paraphrase_queries` — "
        "`tests/fixtures/evaluation/hard_paraphrase_queries.py`, 12 queries "
        "deliberately written to avoid literal keyword overlap with their "
        "correct chunk, per this milestone's own instruction to avoid "
        "evaluation cases retrievable by lexical shortcut alone.",
        "- Metric: Recall@K (K=1,3,5) — per-query binary hit/miss (did any chunk "
        "from the query's expected topic appear in the top-K results), averaged "
        "over all queries in the set. Computed via the real, unmodified "
        "`RetrievalService.search()` — see `tests/evaluation/harness.py`.",
        "- Real model: a small, locally-trained (not downloaded) "
        "`sentence-transformers`-format model — "
        "`scripts/train_local_semantic_model.py` — trained on "
        "`tests/fixtures/evaluation/semantic_training_pairs.py` (36 synthetic "
        "paraphrase pairs), a **disjoint** set from both evaluation query sets "
        "above.",
        "",
        "## Limitations",
        "",
        "- The evaluation corpus and query sets are small and synthetic — results "
        "here are not statistically robust and must not be extrapolated to real "
        "enterprise content, a different domain, or a different query "
        "distribution.",
        "- The real model evaluated here is a small, narrowly-trained "
        "demonstration model, not the recommended production pretrained "
        "checkpoint — see docs/SEMANTIC_EMBEDDING.md's \"Evaluation "
        "methodology\" section for why, and what a real deployment should "
        "expect to do differently (download and evaluate an actual pretrained "
        "sentence-transformers model before relying on this provider in "
        "production).",
        "- No threshold in this report has been tuned or manufactured to make "
        "either provider look better; both are reported as measured.",
        "",
    ]
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n")


def test_zzz_write_semantic_evaluation_report():
    assert _report is not None, "test_semantic_evaluation_runs must run first in this module."
    _write_json_report(_report)
    _write_markdown_report(_report)
    assert REPORT_MD_PATH.exists()
    assert REPORT_JSON_PATH.exists()
