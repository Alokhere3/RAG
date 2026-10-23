"""Public Runtime Configuration API Endpoint.

Conforms to Phase 1 Chunk 1.3 requirements:
- Exposes GET /api/v1/config for browser and client runtime consumption (Layer B)
- Strictly allowlisted response using PublicConfigResponse schema
- Excludes all server-side secrets, database connection strings, and internal credentials
"""

from fastapi import APIRouter
from app.core.config import get_settings
from app.schemas.config import PublicConfigResponse

router = APIRouter(tags=["Configuration"])


@router.get(
    "/config",
    response_model=PublicConfigResponse,
    response_model_by_alias=True,
    summary="Public Application Configuration",
    description=(
        "Returns safe runtime configuration (white-label branding, assistant persona, "
        "theme tokens, and feature flags) for client and browser consumption."
    ),
)
async def get_public_configuration() -> PublicConfigResponse:
    """Return public white-label configuration."""
    settings = get_settings()
    return settings.to_public_config()
