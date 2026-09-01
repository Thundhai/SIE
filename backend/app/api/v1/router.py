from fastapi import APIRouter

from app.api.v1 import (
    api_clients,
    data_sources,
    ingestion,
    intelligence,
    knowledge,
    memberships,
    organizations,
    predictions,
    rag,
    retrieval,
    sites,
)

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(sites.router)
api_router.include_router(data_sources.router)
api_router.include_router(knowledge.router)
api_router.include_router(memberships.router)
api_router.include_router(ingestion.router)
api_router.include_router(retrieval.router)
api_router.include_router(rag.router)
api_router.include_router(intelligence.router)
api_router.include_router(predictions.router)
api_router.include_router(api_clients.router)
