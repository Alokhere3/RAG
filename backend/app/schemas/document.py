"""Pydantic schemas for Document management API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Public document metadata contract. Internal storage key and local disk paths are never exposed."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str = Field(alias="contentType")
    file_size: int = Field(alias="fileSize")
    checksum: str
    uploader_id: uuid.UUID = Field(alias="uploaderId")
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="metadata")


class DocumentListResponse(BaseModel):
    """Paginated list of document metadata."""

    model_config = ConfigDict(populate_by_name=True)

    items: List[DocumentResponse]
    total: int
    limit: int
    offset: int
