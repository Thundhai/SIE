# SIE Backend

SIE (Safety Intelligence Engine) is a multi-tenant API platform for safety data ingestion, governed knowledge management, retrieval, and integration with authorized enterprise applications.

This repository contains the **public SIE service and its integration surface**. Proprietary enterprise analytics, predictive modelling, and other Commercial Core implementation details are maintained in the separate private `Thundhai/SIE-Commercial-Core` repository. Public SIE communicates with that service through the configured integration client and shared contract; it must not embed or reimplement private algorithms.

## Components

- FastAPI REST API under `/api/v1`
- PostgreSQL persistence and Alembic database migrations
- Organization, membership, authorization, and audit infrastructure
- Document ingestion, knowledge storage, and retrieval
- Optional integration with the separately deployed Commercial Core service

The API's live OpenAPI schema at `/openapi.json` and interactive documentation at `/docs` are authoritative for the routes available in a running deployment. Commercial Core-backed capabilities require a correctly configured and reachable Commercial Core deployment; those routes may return a service-unavailable response when the dependency is not configured or reachable.

## Requirements

- Python 3.12
- PostgreSQL 16
- The PostgreSQL `pgvector` extension

## Local setup

From the repository root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Configure `.env` for your local PostgreSQL instance. The example file contains development-only defaults and placeholders; do not put production credentials in source control.

Apply migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to inspect the live API. Ensure that the environment's authentication and CORS settings are appropriate before exposing the service beyond local development.

## Tests

From `backend/` with the dependencies installed:

```bash
python -m pytest -q
alembic check
```

The full CI workflow provisions PostgreSQL with pgvector, applies migrations to a fresh database, and runs the backend test suite. PostgreSQL-dependent tests require a reachable PostgreSQL/pgvector service.

## Public documentation

- [Developer integration guide](docs/INTEGRATION_GUIDE.md)
- [Performance baseline](docs/PERFORMANCE_BASELINE.md)
- [Public architecture boundary](docs/PUBLIC_ARCHITECTURE_BOUNDARY.md)

## Security and intellectual-property boundary

- Never commit secrets, private customer datasets, production environment files, or access tokens.
- Use synthetic or explicitly authorized data in examples and tests.
- Do not add Commercial Core algorithms, internal scoring logic, private model artifacts, or proprietary evaluation reports to this repository.
- Keep public DTOs and observable API behavior separate from private implementation mechanics.
- Treat the live API schema and versioned integration contract as the public interface.

This README intentionally documents the public service at an integration and operations level rather than reproducing internal implementation specifications.
