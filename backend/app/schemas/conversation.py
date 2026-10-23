"""Pydantic schemas for conversations and messages."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """Payload to initiate a new conversation."""

    title: Optional[str] = Field(
        default="New Conversation",
        max_length=255,
        description="Optional title for the conversation",
    )


class ConversationResponse(BaseModel):
    """Public representation of a conversation."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MessageCreate(BaseModel):
    """User prompt submission to a conversation."""

    content: str = Field(
        min_length=1,
        max_length=4000,
        description="Prompt or question submitted by the user",
    )


class MessageResponse(BaseModel):
    """Message turn representation."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: Optional[List[Dict[str, Any]]] = None
    latency_ms: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    """Paginated list of messages within a conversation."""

    items: List[MessageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
