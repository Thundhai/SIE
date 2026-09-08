from fastapi import APIRouter

from app.api.v1 import (
    actions,
    api_clients,
    auth,
    data_ingestion,
    data_sources,
    events,
    ingestion,
    intelligence,
    intelligence_decisions,
    knowledge,
    memberships,
    model_governance,
    organizations,
    predictions,
    projects,
    rag,
    retrieval,
    risk_assessments,
    sites,
)

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(sites.router)
api_router.include_router(projects.router)
api_router.include_router(data_sources.router)
api_router.include_router(knowledge.router)
api_router.include_router(memberships.router)
api_router.include_router(ingestion.router)
api_router.include_router(data_ingestion.router)
api_router.include_router(retrieval.router)
api_router.include_router(rag.router)
api_router.include_router(intelligence.router)
api_router.include_router(intelligence_decisions.router)
api_router.include_router(events.router)
api_router.include_router(actions.router)
api_router.include_router(predictions.router)
api_router.include_router(model_governance.router)
api_router.include_router(risk_assessments.router)
api_router.include_router(api_clients.router)
api_router.include_router(auth.router)
