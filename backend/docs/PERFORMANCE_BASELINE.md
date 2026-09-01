# SIE Performance Baseline

Generated 2026-09-01T21:04:58.445219+00:00 by `tests/test_performance_baseline.py` — see that file's own docstring for exactly what is and is not measured here.

**These are local development machine numbers, not a load test and not a production capacity or SLA claim.** Single-request timings, no concurrency, no production data volume, no warmed production hardware. Useful only for spotting a gross future regression.

| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |
|---|---|---|---|---|---|---|
| Ingestion: POST /intelligence/events (single event) | 20 | 24.56 | 25.02 | 21.24 | 30.08 | HTTP + SQLite |
| Analytics: GET /intelligence/analytics/summary (50 seeded events) | 20 | 34.51 | 34.13 | 29.93 | 38.48 | HTTP + SQLite |
| Prediction: POST /intelligence/predictions | 10 | 35.59 | 35.61 | 31.15 | 41.47 | HTTP + SQLite; each call trains no new model |
| Retrieval: retrieval_service.search() (20 seeded chunks) | 10 | 5.75 | 5.38 | 3.65 | 13.77 | real PostgreSQL + pgvector, service layer only (no HTTP) |
| RAG: rag_service.query() (20 seeded chunks, fake LLM provider) | 10 | 7.68 | 8.01 | 6.15 | 8.54 | real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline) |
