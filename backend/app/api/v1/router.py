from fastapi import APIRouter

from app.api.v1 import data_sources, ingestion, knowledge, memberships, organizations, sites

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(sites.router)
api_router.include_router(data_sources.router)
api_router.include_router(knowledge.router)
api_router.include_router(memberships.router)
api_router.include_router(ingestion.router)
