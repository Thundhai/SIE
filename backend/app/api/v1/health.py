"""Health endpoints — Intelligence Platform Integration & Enterprise API
v0.1, items 33-34.

    GET /health        -> liveness (unchanged since Foundation v0.1 — kept for compatibility)
    GET /health/live    -> liveness, explicit
    GET /health/ready   -> readiness (checks dependencies)

**Liveness never depends on anything external** (item 34's own
instruction) — `/health` and `/health/live` do not touch the database or
any configured provider; a process that can answer HTTP at all is
"alive" by definition, and a liveness probe failing for a reason other
than "this process is unresponsive" is exactly the kind of over-eager
restart-loop item 34 warns against.

**Readiness checks real dependencies without leaking how they failed.**
`/health/ready` currently checks PostgreSQL connectivity (`SELECT 1`) —
the one dependency every request in this codebase genuinely needs.
pgvector and a configured external LLM are deliberately NOT included:
pgvector is a PostgreSQL extension already implied by the database check
above (a reachable database in this codebase always has it, per every
migration since 0006), and the configured LLM/embedding provider
(`app.llm.provider`/`app.embeddings.provider`) defaults to a fully
offline, dependency-free implementation (`fake`/`hashing`) in every
environment this codebase ships configured for — an *optional* external
provider failing must never fail readiness either (item 34's own
instruction: "do not make liveness fail simply because an optional
external provider is unavailable" applies with equal force to
readiness, for a dependency this codebase doesn't require to serve a
request at all). Each check reports only a fixed, generic name and
UP/DOWN — never the underlying exception message, connection string, or
stack trace.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Deliberately has no database dependency. Kept
    unchanged (item 35's "do not break existing v1 consumers") —
    `/health/live` below is the same check, added under this milestone's
    more explicit naming."""
    return {"status": "ok"}


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


def _check_database(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure here means simply "not ready", never leaked or re-raised
        return False


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> JSONResponse:
    """Uses the same `Depends(get_db)` every other route in this codebase
    does — deliberately, not a standalone `SessionLocal()` — so this
    check targets whatever database the running process is actually
    configured against (and, in this test suite, the same overridden
    SQLite session every other test uses), never a second, independent
    connection path that could report a misleadingly different answer."""
    checks = {"database": "UP" if _check_database(db) else "DOWN"}
    overall_ok = all(v == "UP" for v in checks.values())
    # 503 (not 200) when not ready -- the status code itself is what a
    # load balancer / orchestrator readiness probe actually keys off;
    # the body is for a human/dashboard reading it directly.
    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={"status": "ready" if overall_ok else "not_ready", "checks": checks},
    )
