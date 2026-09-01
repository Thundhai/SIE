# SIE Performance Baseline

Generated 2026-09-01T20:02:04.665265+00:00 by `tests/test_performance_baseline.py` — see that file's own docstring for exactly what is and is not measured here.

**These are local development machine numbers, not a load test and not a production capacity or SLA claim.** Single-request timings, no concurrency, no production data volume, no warmed production hardware. Useful only for spotting a gross future regression.

| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |
|---|---|---|---|---|---|---|
| Ingestion: POST /intelligence/events (single event) | 20 | 21.55 | 21.31 | 18.86 | 24.11 | HTTP + SQLite |
| Analytics: GET /intelligence/analytics/summary (50 seeded events) | 20 | 48.14 | 34.34 | 31.29 | 303.22 | HTTP + SQLite |
| Prediction: POST /intelligence/predictions | 10 | 34.67 | 34.2 | 31.89 | 40.91 | HTTP + SQLite; each call trains no new model |
| Retrieval: retrieval_service.search() (20 seeded chunks) | 10 | 8.64 | 4.99 | 4.56 | 26.64 | real PostgreSQL + pgvector, service layer only (no HTTP) |
| RAG: rag_service.query() (20 seeded chunks, fake LLM provider) | 10 | 9.12 | 8.79 | 8.43 | 11.22 | real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline) |
