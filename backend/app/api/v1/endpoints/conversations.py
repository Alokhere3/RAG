"""Conversations and Chat REST API endpoints."""

import logging
import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import (
    ChatResponse,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversation_service import conversation_service
from app.services.rag.sanitizer import sanitize_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


from typing import Optional

@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(
    payload: Optional[ConversationCreate] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Initialize a persistent conversation session."""
    title = payload.title if payload else "New Conversation"
    conversation = await conversation_service.create_conversation(
        session=session,
        user=current_user,
        title=title,
    )
    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )



@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List conversations",
)
async def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """Fetch paginated conversations belonging to the authenticated user."""
    items, total = await conversation_service.list_conversations(
        session=session,
        user=current_user,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return ConversationListResponse(
        items=[
            ConversationResponse(
                id=c.id,
                user_id=c.user_id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=len(c.messages) if hasattr(c, "messages") and c.messages else 0,
            )
            for c in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get conversation metadata",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Fetch a single conversation by ID with ownership enforcement."""
    conversation = await conversation_service.get_conversation(
        session=session,
        user=current_user,
        conversation_id=conversation_id,
    )
    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages) if hasattr(conversation, "messages") and conversation.messages else 0,
    )


@router.delete(
    "/{conversation_id}",
    summary="Delete conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Delete conversation and all its messages."""
    await conversation_service.delete_conversation(
        session=session,
        user=current_user,
        conversation_id=conversation_id,
    )
    return {"deleted": True, "conversation_id": str(conversation_id)}


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message and generate grounded answer",
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Post prompt to conversation, execute RAG retrieval, and return public answer-only response."""
    _, assistant_msg = await conversation_service.post_message(
        session=session,
        user=current_user,
        conversation_id=conversation_id,
        content=payload.content,
    )
    return ChatResponse(answer=assistant_msg.content)


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="List conversation messages",
)
async def list_messages(
    conversation_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Page size"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """Fetch chronological message history within a conversation."""
    items, total = await conversation_service.list_messages(
        session=session,
        user=current_user,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return MessageListResponse(
        items=[
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=sanitize_answer(m.content),
                created_at=m.created_at,
            )
            for m in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
