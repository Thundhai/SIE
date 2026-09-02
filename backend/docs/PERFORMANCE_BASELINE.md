# SIE Performance Baseline

Generated 2026-09-02T02:11:27.158854+00:00 by `tests/test_performance_baseline.py` — see that file's own docstring for exactly what is and is not measured here.

**These are local development machine numbers, not a load test and not a production capacity or SLA claim.** Single-request timings, no concurrency, no production data volume, no warmed production hardware. Useful only for spotting a gross future regression.

| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |
|---|---|---|---|---|---|---|
| Ingestion: POST /intelligence/events (single event) | 20 | 15.05 | 13.96 | 12.84 | 34.29 | HTTP + SQLite |
| Analytics: GET /intelligence/analytics/summary (50 seeded events) | 20 | 23.52 | 22.66 | 21.56 | 34.79 | HTTP + SQLite |
| Prediction: POST /intelligence/predictions | 10 | 43.86 | 25.88 | 24.73 | 194.17 | HTTP + SQLite; each call trains no new model |
| Retrieval: retrieval_service.search() (20 seeded chunks) | 10 | 3.45 | 2.98 | 2.44 | 7.75 | real PostgreSQL + pgvector, service layer only (no HTTP) |
| RAG: rag_service.query() (20 seeded chunks, fake LLM provider) | 10 | 4.8 | 4.75 | 4.37 | 5.86 | real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline) |
