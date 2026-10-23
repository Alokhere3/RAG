"""Pydantic schemas for authentication requests, responses, and user profiles."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    """Public authenticated user profile contract."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: Optional[str] = Field(default=None, alias="displayName")
    role: str
    status: str
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    last_login_at: Optional[datetime] = Field(default=None, alias="lastLoginAt")


class LoginRequest(BaseModel):
    """User credentials submitted for login."""

    model_config = ConfigDict(populate_by_name=True)

    email: str = Field(description="User email address")
    password: str = Field(description="Plaintext password to verify")


class LoginResponse(BaseModel):
    """Successful authentication response containing user profile and access token."""

    model_config = ConfigDict(populate_by_name=True)

    user: UserResponse
    access_token: str = Field(alias="accessToken", description="Short-lived JWT access token")
    token_type: str = Field(default="bearer", alias="tokenType", description="Token authentication scheme")


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(populate_by_name=True)

    message: str
