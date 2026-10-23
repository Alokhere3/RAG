"""Public Configuration Schemas.

Defines the contract for safe, browser-consumable public configuration (Layer B).
Strictly separates public white-label branding and feature flags from private server infrastructure.
"""

from pydantic import BaseModel, ConfigDict, Field


class ApplicationPublicConfig(BaseModel):
    """Public application identity and runtime metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Platform application name")
    version: str = Field(description="Semantic software release version")
    environment: str = Field(description="Active deployment environment name")


class OrganizationPublicConfig(BaseModel):
    """Public organization / tenant branding identity."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Client organization or tenant name")
    logo_url: str = Field(
        default="",
        alias="logoUrl",
        description="URL for tenant header/branding logo",
    )
    website_url: str = Field(
        default="",
        alias="websiteUrl",
        description="Tenant website URL",
    )


class AssistantPublicConfig(BaseModel):
    """Public virtual assistant identity and personality."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Name of the AI assistant")
    description: str = Field(
        default="",
        description="Brief introductory description or tagline for the assistant",
    )
    avatar_url: str = Field(
        default="",
        alias="avatarUrl",
        description="URL for assistant avatar image",
    )


class BrandingPublicConfig(BaseModel):
    """Public design tokens and visual theme configuration."""

    model_config = ConfigDict(populate_by_name=True)

    primary_color: str = Field(
        alias="primaryColor",
        description="Primary brand color (hex format, e.g. #2563EB)",
    )
    secondary_color: str = Field(
        alias="secondaryColor",
        description="Secondary brand color (hex format, e.g. #1E293B)",
    )
    accent_color: str = Field(
        alias="accentColor",
        description="Accent highlight color (hex format, e.g. #3B82F6)",
    )
    favicon_url: str = Field(
        default="",
        alias="faviconUrl",
        description="URL for browser favicon icon",
    )


class FeaturesPublicConfig(BaseModel):
    """Public feature flag enablement states."""

    model_config = ConfigDict(populate_by_name=True)

    chat: bool = Field(default=False, description="Whether the chat interface is enabled")
    documents: bool = Field(
        default=False, description="Whether document management interface is enabled"
    )
    ingestion: bool = Field(
        default=True, description="Whether document ingestion pipeline is enabled"
    )


class PublicConfigResponse(BaseModel):
    """Root response model for GET /api/v1/config.

    Conforms to Phase 1 Layer B specification.
    Guarantees no server secrets (DATABASE_URL, REDIS_URL, API keys) can enter the payload.
    """

    model_config = ConfigDict(populate_by_name=True)

    application: ApplicationPublicConfig
    organization: OrganizationPublicConfig
    assistant: AssistantPublicConfig
    branding: BrandingPublicConfig
    features: FeaturesPublicConfig
