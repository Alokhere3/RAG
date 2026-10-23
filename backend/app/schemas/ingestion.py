"""Pydantic schemas for Ingestion Job requests and responses."""

from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class IngestionJobResponse(BaseModel):
    """Safe public representation of an ingestion job."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    status: str
    attempt_count: int = Field(alias="attemptCount")
    max_attempts: int = Field(alias="maxAttempts")
    error_code: Optional[str] = Field(default=None, alias="errorCode")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")
    parser_name: Optional[str] = Field(default=None, alias="parserName")
    parser_version: Optional[str] = Field(default=None, alias="parserVersion")
    page_count: Optional[int] = Field(default=None, alias="pageCount")
    char_count: Optional[int] = Field(default=None, alias="charCount")
    created_at: datetime = Field(alias="createdAt")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")


class DocumentIngestionHistoryResponse(BaseModel):
    """Current status and execution history for document ingestion."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    document_status: str = Field(alias="documentStatus")
    current_job: Optional[IngestionJobResponse] = Field(default=None, alias="currentJob")
    history: List[IngestionJobResponse] = Field(default_factory=list)


class TriggerIngestionRequest(BaseModel):
    """Optional payload when triggering re-ingestion."""

    force_reprocess: bool = Field(default=False, alias="forceReprocess")
