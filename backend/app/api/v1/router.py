"""API v1 master router."""

from fastapi import APIRouter
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.config import router as config_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.ingestion import router as ingestion_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(config_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(ingestion_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Administration"])


