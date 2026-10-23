"""Health and Readiness API Endpoints."""

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.services.health import HealthService

router = APIRouter(tags=["Health"])


class StatusResponse(BaseModel):
    status: str


class ReadinessDependencies(BaseModel):
    database: str
    redis: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: ReadinessDependencies


def get_health_service() -> HealthService:
    """Dependency injector for HealthService."""
    return HealthService()


@router.get(
    "/health",
    response_model=StatusResponse,
    summary="Application Health",
    description="Reports basic application health.",
)
async def health() -> StatusResponse:
    return StatusResponse(status="ok")


@router.get(
    "/health/live",
    response_model=StatusResponse,
    summary="Process Liveness",
    description="Probes process liveness independently of external dependencies.",
)
async def liveness() -> StatusResponse:
    return StatusResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Application Readiness",
    description="Probes readiness of PostgreSQL and Redis dependencies.",
)
async def readiness(
    response: Response,
    service: HealthService = Depends(get_health_service),
) -> ReadinessResponse:
    readiness_data = await service.get_readiness()
    if readiness_data["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=readiness_data["status"],
        dependencies=ReadinessDependencies(**readiness_data["dependencies"]),
    )
