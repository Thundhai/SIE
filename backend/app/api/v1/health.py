from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Deliberately has no database dependency."""
    return {"status": "ok"}
