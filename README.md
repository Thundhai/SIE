# SIE — Safety Intelligence Engine

SIE is a multi-tenant Enterprise Safety Intelligence Platform: safety-event management, risk assessment, and action/intervention tracking for high-hazard industries, with ranked attention and enterprise risk intelligence surfaced through a dedicated Intelligence workspace.

This repository is the **public SIE application** — the frontend, the core API, and the integration boundary. Proprietary enterprise analytics, predictive modelling, and other advanced-intelligence implementation details live in a separate, private `Thundhai/SIE-Commercial-Core` repository. Public SIE communicates with that service through a versioned shared contract and a dedicated HTTP integration client; it never embeds or reimplements private algorithms. See `backend/docs/PUBLIC_ARCHITECTURE_BOUNDARY.md` for the architectural rationale.

Capabilities backed by Commercial Core require a correctly configured, reachable Commercial Core deployment. Without one, those routes return a service-unavailable response rather than failing silently or fabricating data.

## Repository layout

- `backend/` — FastAPI REST API (Python 3.12), PostgreSQL + pgvector persistence, Alembic migrations. See `backend/README.md` for backend-specific setup.
- `src/` — React/TypeScript frontend (Vite). See `docs/FRONTEND_ARCHITECTURE.md`.
- `docs/` — architecture, CI, production auth, and domain documentation, including the project `docs/ROADMAP.md`.
- `.github/workflows/` — CI (backend tests + migrations, frontend tests + typecheck + build).

## Getting started

Backend setup: see `backend/README.md`.

Frontend setup, from the repository root:

```bash
bun install
bun run dev
```

Frontend tests, type-check, and build:

```bash
bun run test
bun run lint
bun run build
```

## Documentation

- [Project roadmap](docs/ROADMAP.md)
- [Frontend architecture](docs/FRONTEND_ARCHITECTURE.md)
- [CI](docs/CI.md)
- [Production auth](docs/PRODUCTION_AUTH.md)
- [Actions domain](docs/ACTIONS_DOMAIN.md)
- [Enterprise API](docs/ENTERPRISE_API.md)
- [Development setup](docs/DEVELOPMENT_SETUP.md)

## License

Proprietary — All Rights Reserved. See [LICENSE](LICENSE).
