"""Performance baseline — Intelligence Platform Integration & Enterprise
API v0.1, item 43: "do not prematurely optimize; establish basic
benchmarks (ingestion, analytics, retrieval, RAG, prediction); record
baseline latency; never claim production-scale performance from local
dev tests."

**What this measures, and what it deliberately does not.** Ingestion,
analytics, and prediction are measured end to end over real HTTP
(`client`), against SQLite (the same engine the rest of this test suite
runs against) — this captures the FastAPI/middleware/service overhead
this milestone actually added (request-id, rate limiting, size limits,
auth, envelope, audit logging), not real production I/O latency.
Retrieval and RAG are measured at the service layer directly, against
real PostgreSQL + pgvector (`pg_session`, `@requires_postgres` — skipped,
not failed, where no server is reachable) rather than SQLite, since
SQLite cannot execute the `<=>`/`.cosine_distance()` operators either one
needs (see `tests/postgres_support.py`); this means the RAG/retrieval
numbers do *not* include the HTTP layer the other three do.

**None of this is a load test.** No concurrency, no connection pooling
under contention, no realistic production data volume, no warmed-up
production hardware. It is a handful of single-request timings on
whatever machine happens to run the suite, useful only for spotting a
gross, order-of-magnitude regression later — never cited as a
production capacity or SLA number. Results are written to
`docs/PERFORMANCE_BASELINE.md` (regenerated each run) and printed with
`pytest -s`.
"""

import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site
from tests.postgres_support import requires_postgres
from tests.test_predictions_api import _deployed_model, _make_authorized_user

REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "PERFORMANCE_BASELINE.md"

_results: dict[str, dict] = {}


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _time_it(fn, iterations: int) -> dict:
    durations_ms = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        durations_ms.append((time.perf_counter() - started) * 1000)
    durations_ms.sort()
    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(durations_ms), 2),
        "median_ms": round(statistics.median(durations_ms), 2),
        "min_ms": round(durations_ms[0], 2),
        "max_ms": round(durations_ms[-1], 2),
    }


def _record(name: str, stats: dict, note: str = "") -> None:
    _results[name] = {**stats, "note": note}
    print(f"\n[perf] {name}: {stats}" + (f"  ({note})" if note else ""))
    # A loose sanity ceiling only -- catches a gross regression (an
    # accidental N+1 query, a synchronous network call sneaking into a
    # hot path), never a throughput target.
    assert stats["mean_ms"] < 5000, f"{name} mean latency {stats['mean_ms']}ms far exceeds a sane local-dev ceiling"


def _write_report() -> None:
    lines = [
        "# SIE Performance Baseline",
        "",
        (
            f"Generated {datetime.now(timezone.utc).isoformat()} by "
            "`tests/test_performance_baseline.py` — see that file's own docstring "
            "for exactly what is and is not measured here."
        ),
        "",
        (
            "**These are local development machine numbers, not a load test and "
            "not a production capacity or SLA claim.** Single-request timings, no "
            "concurrency, no production data volume, no warmed production "
            "hardware. Useful only for spotting a gross future regression."
        ),
        "",
        "| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, stats in _results.items():
        lines.append(
            f"| {name} | {stats['iterations']} | {stats['mean_ms']} | {stats['median_ms']} | "
            f"{stats['min_ms']} | {stats['max_ms']} | {stats['note']} |"
        )
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines))


# --- Ingestion (HTTP, SQLite) --------------------------------------------------------------


def test_ingestion_baseline(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Perf Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    counter = iter(range(1_000_000))

    def _ingest_one():
        response = client.post(
            "/api/v1/intelligence/events",
            json={
                "event_type": "NEAR_MISS",
                "event_time": "2026-01-01T00:00:00Z",
                "source_system": "perf-baseline",
                "source_record_id": f"perf-{next(counter)}",
            },
            headers=_bearer(credential),
        )
        assert response.status_code == 200

    stats = _time_it(_ingest_one, iterations=20)
    _record("Ingestion: POST /intelligence/events (single event)", stats, note="HTTP + SQLite")


# --- Analytics (HTTP, SQLite) --------------------------------------------------------------


def test_analytics_summary_baseline(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = _make_authorized_user(db_session, org.id)
    now = datetime.now(timezone.utc)
    for i in range(50):
        event = make_safety_event(
            organization_id=org.id,
            site_id=site.id,
            event_type="INCIDENT" if i % 5 else "NEAR_MISS",
            event_time=now,
            ingestion_time=now,
            source_record_id=f"analytics-perf-{i}",
        )
        db_session.add(event)
    db_session.commit()

    def _read_summary():
        response = client.get(
            f"/api/v1/intelligence/analytics/summary?organization_id={org.id}", headers=dev_auth_headers(user.id)
        )
        assert response.status_code == 200

    stats = _time_it(_read_summary, iterations=20)
    _record("Analytics: GET /intelligence/analytics/summary (50 seeded events)", stats, note="HTTP + SQLite")


# --- Predictions (HTTP, SQLite) ------------------------------------------------------------


def test_prediction_creation_baseline(client, db_session):
    org, site, _entry, as_of = _deployed_model(db_session, seed=9001)
    user = _make_authorized_user(db_session, org.id)

    def _create_one():
        response = client.post(
            f"/api/v1/intelligence/predictions?organization_id={org.id}",
            json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
            headers=dev_auth_headers(user.id),
        )
        assert response.status_code == 200

    stats = _time_it(_create_one, iterations=10)
    _record("Prediction: POST /intelligence/predictions", stats, note="HTTP + SQLite; each call trains no new model")


# --- Retrieval / RAG (service layer, real PostgreSQL + pgvector) -----------------------------


@requires_postgres
def test_retrieval_and_rag_baseline(pg_session):
    from app.core.config import settings
    from app.embeddings.embedding_service import embedding_service
    from app.embeddings.provider import HashingEmbeddingProvider
    from tests.test_retrieval_service import seed_chunk

    provider = HashingEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)
    text = "Workers must wear a full-body harness when working at height above 1.8 metres."
    from app.models.knowledge_chunk import KnowledgeChunk

    for i in range(20):
        seed_chunk(pg_session, text=f"{text} (chunk {i})", embed=False)
    chunks = pg_session.query(KnowledgeChunk).all()
    for chunk in chunks:
        embedding_service.embed_chunk(pg_session, chunk=chunk, provider=provider, force=True)

    from app.retrieval.retrieval_service import retrieval_service

    def _search():
        response = retrieval_service.search(
            pg_session, query_text=text, allowed_organization_id=None, provider=provider
        )
        assert response.result_count > 0

    stats = _time_it(_search, iterations=10)
    _record(
        "Retrieval: retrieval_service.search() (20 seeded chunks)",
        stats,
        note="real PostgreSQL + pgvector, service layer only (no HTTP)",
    )

    from app.rag.rag_service import rag_service

    def _rag_query():
        response = rag_service.query(
            pg_session, query_text=text, allowed_organization_id=None, embedding_provider=provider
        )
        assert response.evidence_count > 0

    stats = _time_it(_rag_query, iterations=10)
    _record(
        "RAG: rag_service.query() (20 seeded chunks, fake LLM provider)",
        stats,
        note="real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline)",
    )


# --- Report -----------------------------------------------------------------------------


def test_zzz_write_performance_report():
    """Named to sort/collect after the measurement tests above within
    this module (pytest preserves file-definition order by default) --
    writes whatever has been recorded so far, even if the PostgreSQL-only
    tests above were skipped."""
    _write_report()
    assert REPORT_PATH.exists()
