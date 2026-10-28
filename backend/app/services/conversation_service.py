from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.models.conversation import Conversation, Message
from app.models.user import User, UserRole
from app.services.auth.access_control import AccessControlService
from app.services.rag.sanitizer import sanitize_answer
from app.services.rag.schemas import RagQueryRequest
from app.services.rag.service import RagService, INSUFFICIENT_EVIDENCE_ANSWER

logger = logging.getLogger(__name__)


class ConversationService:
    """Manages conversations, message history, and grounded RAG responses."""

    def __init__(self, rag_service: Optional[RagService] = None) -> None:
        self._rag_service = rag_service or RagService()

    @property
    def rag_service(self) -> RagService:
        return self._rag_service

    async def create_conversation(
        self,
        session: AsyncSession,
        user: User,
        title: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation session for the authenticated user."""
        clean_title = (title.strip() if title and title.strip() else "New Conversation")[:255]
        conversation = Conversation(
            user_id=user.id,
            title=clean_title,
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        logger.info("CONVERSATION_CREATED conv_id=%s user_id=%s", conversation.id, user.id)
        return conversation

    async def list_conversations(
        self,
        session: AsyncSession,
        user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Conversation], int]:
        """List own conversations with stable pagination (C002)."""
        offset = (page - 1) * page_size

        count_stmt = select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one()

        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        res = await session.execute(stmt)
        conversations = res.scalars().all()

        return list(conversations), total

    async def get_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
    ) -> Conversation:
        """Get a single conversation enforcing user ownership boundaries (C003, C004)."""
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        res = await session.execute(stmt)
        conversation = res.scalar_one_or_none()


        if not conversation:
            raise NotFoundError("Conversation not found.")

        # Enforce conversation ownership boundaries via centralized access control
        AccessControlService.authorize_conversation_access(user, conversation)

        return conversation

    async def delete_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
    ) -> bool:
        """Delete conversation and cascade messages following retention policy (C009)."""
        # Enforce existence and ownership
        conversation = await self.get_conversation(session, user, conversation_id)

        await session.delete(conversation)
        await session.commit()

        logger.info("CONVERSATION_DELETED conv_id=%s user_id=%s", conversation_id, user.id)
        return True

    async def post_message(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        content: str,
    ) -> Tuple[Message, Message]:
        """Post a user prompt, execute grounded RAG, and persist both turns (C005, C006, C007)."""
        # 1. Enforce existence and authorization
        conversation = await self.get_conversation(session, user, conversation_id)

        clean_content = content.strip()

        # 2. Persist user message
        now = datetime.now(timezone.utc)
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=clean_content,
            created_at=now,
        )
        session.add(user_message)
        await session.flush()

        # 3. Invoke RAG pipeline
        rag_request = RagQueryRequest(query=clean_content)
        rag_answer = await self._rag_service.answer_query(
            session=session,
            user=user,
            request=rag_request,
        )

        # 4. Serialize citations
        citations_data = [c.model_dump(mode="json") for c in rag_answer.citations]

        # 5. Extract token usage if available
        prompt_tokens = rag_answer.usage.prompt_tokens if rag_answer.usage else None
        comp_tokens = rag_answer.usage.completion_tokens if rag_answer.usage else None
        tot_tokens = rag_answer.usage.total_tokens if rag_answer.usage else None

        # 6. Sanitize answer for persistence and user presentation
        sanitized_answer = sanitize_answer(rag_answer.answer)
        asst_now = datetime.now(timezone.utc)
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=sanitized_answer,
            citations=citations_data,
            latency_ms=rag_answer.latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            total_tokens=tot_tokens,
            created_at=asst_now,
        )
        session.add(assistant_message)

        # 7. Update conversation title if default
        if conversation.title == "New Conversation":
            first_words = clean_content[:40]
            conversation.title = f"{first_words}..." if len(clean_content) > 40 else first_words

        conversation.updated_at = func.now()

        await session.commit()
        await session.refresh(user_message)
        await session.refresh(assistant_message)

        logger.info(
            "MESSAGE_TURN_PERSISTED conv_id=%s user_msg_id=%s asst_msg_id=%s citations=%d",
            conversation.id,
            user_message.id,
            assistant_message.id,
            len(citations_data),
        )

        return user_message, assistant_message

    async def list_messages(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Message], int]:
        """Fetch messages within a conversation with stable ascending chronological ordering (C010)."""
        # Enforce authorization
        await self.get_conversation(session, user, conversation_id)

        offset = (page - 1) * page_size

        count_stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one()

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(
                Message.created_at.asc(),
                sa.case((Message.role == "user", 1), else_=2).asc(),
                Message.id.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        res = await session.execute(stmt)
        messages = res.scalars().all()

        return list(messages), total


conversation_service = ConversationService()
