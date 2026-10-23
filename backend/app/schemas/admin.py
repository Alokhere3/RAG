"""Admin operational request and response Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole, UserStatus


class AdminUserCreateRequest(BaseModel):
    """Admin request schema to register a new user."""

    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = Field(default=UserRole.USER)


class AdminRoleUpdateRequest(BaseModel):
    """Admin request schema to update a user's role."""

    role: UserRole


class AdminStatusUpdateRequest(BaseModel):
    """Admin request schema to activate or suspend a user."""

    status: UserStatus


class AdminUserResponse(BaseModel):
    """Public safe representation of a user in admin views."""

    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserListResponse(BaseModel):
    """Paginated list of system users."""

    items: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminDiagnosticsResponse(BaseModel):
    """Non-secret configuration diagnostics."""

    application: Dict[str, Any]
    security: Dict[str, Any]
    embedding: Dict[str, Any]
    llm: Dict[str, Any]
    storage_and_ingestion: Dict[str, Any]
    features: Dict[str, Any]
