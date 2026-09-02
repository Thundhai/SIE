# SIE Performance Baseline

Generated 2026-09-02T00:44:50.636706+00:00 by `tests/test_performance_baseline.py` — see that file's own docstring for exactly what is and is not measured here.

**These are local development machine numbers, not a load test and not a production capacity or SLA claim.** Single-request timings, no concurrency, no production data volume, no warmed production hardware. Useful only for spotting a gross future regression.

| Operation | Iterations | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Notes |
|---|---|---|---|---|---|---|
| Ingestion: POST /intelligence/events (single event) | 20 | 13.95 | 13.16 | 11.64 | 30.22 | HTTP + SQLite |
| Analytics: GET /intelligence/analytics/summary (50 seeded events) | 20 | 18.77 | 18.35 | 17.37 | 26.1 | HTTP + SQLite |
| Prediction: POST /intelligence/predictions | 10 | 32.32 | 20.76 | 19.74 | 126.29 | HTTP + SQLite; each call trains no new model |
| Retrieval: retrieval_service.search() (20 seeded chunks) | 10 | 3.2 | 2.87 | 2.25 | 7.17 | real PostgreSQL + pgvector, service layer only (no HTTP) |
| RAG: rag_service.query() (20 seeded chunks, fake LLM provider) | 10 | 5.19 | 5.0 | 4.75 | 6.53 | real PostgreSQL + pgvector, service layer only (no HTTP); LLM_PROVIDER=fake (offline) |
