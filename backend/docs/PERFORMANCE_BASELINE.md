# SIE Performance Baseline

Generated 2026-09-01T20:20:26.741941+00:00 by `tests/test_performance_baseline.py` — see that file's own docstring for exactly what is and is not measured here.

**These are local development machine numbers, not a load test and not a production capacity or SLA claim.** Single-request timings, no concurrency, no production data volume, no warmed production hardware. Useful only for spotting a gross future regression.

| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |
|---|---|---|---|---|---|---|
| Ingestion: POST /intelligence/events (single event) | 20 | 18.15 | 18.24 | 16.55 | 20.58 | HTTP + SQLite |
| Analytics: GET /intelligence/analytics/summary (50 seeded events) | 20 | 30.26 | 29.88 | 28.24 | 34.87 | HTTP + SQLite |
| Prediction: POST /intelligence/predictions | 10 | 32.93 | 32.66 | 30.59 | 38.2 | HTTP + SQLite; each call trains no new model |
| Retrieval: retrieval_service.search() (20 seeded chunks) | 10 | 6.15 | 4.68 | 3.56 | 18.58 | real PostgreSQL + pgvector, service layer only (no HTTP) |
| RAG: rag_service.query() (20 seeded chunks, fake LLM provider) | 10 | 7.2 | 7.18 | 6.44 | 8.02 | real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline) |
