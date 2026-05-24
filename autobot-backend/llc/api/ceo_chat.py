# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC CEO Chat API routes (GH#8233).

Routes:
  POST  /llc/companies/{company_id}/ceo-chat/threads   — create thread
  GET   /llc/companies/{company_id}/ceo-chat/threads   — list threads (recent first)
  GET   /llc/ceo-chat/threads/{thread_id}              — thread with messages + entity link
  POST  /llc/ceo-chat/threads/{thread_id}/messages     — send message → resolve to work object
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session

from ..services.ceo_chat import CeoChatService

router = APIRouter(tags=["llc-ceo-chat"])

_get_service = lazy_singleton(CeoChatService)


def _service() -> CeoChatService:
    return _get_service()


# ------------------------------------------------------------------ Schemas


class ThreadCreate(BaseModel):
    title: str
    created_by_user_id: Optional[str] = None


class MessageSend(BaseModel):
    message: str
    user_id: Optional[str] = None
    company_name: str = "the company"


class MessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    author_type: str
    author_user_id: Optional[uuid.UUID]
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    resolved_entity_type: Optional[str]
    resolved_entity_id: Optional[uuid.UUID]
    created_by_user_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ThreadWithMessages(ThreadResponse):
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.post(
    "/companies/{company_id}/ceo-chat/threads",
    response_model=ThreadResponse,
    status_code=201,
)
async def create_thread(
    company_id: str,
    body: ThreadCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ThreadResponse:
    svc = _service()
    async with session.begin():
        thread = await svc.create_thread(
            session,
            company_id=company_id,
            title=body.title,
            created_by_user_id=body.created_by_user_id,
        )
    return ThreadResponse.model_validate(thread)


@router.get(
    "/companies/{company_id}/ceo-chat/threads",
    response_model=List[ThreadResponse],
)
async def list_threads(
    company_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[ThreadResponse]:
    svc = _service()
    async with session.begin():
        threads = await svc.list_threads(session, company_id=company_id)
    return [ThreadResponse.model_validate(t) for t in threads]


@router.get(
    "/ceo-chat/threads/{thread_id}",
    response_model=ThreadWithMessages,
)
async def get_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> ThreadWithMessages:
    svc = _service()
    async with session.begin():
        thread = await svc.get_thread(session, thread_id=thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadWithMessages.model_validate(thread)


@router.post(
    "/ceo-chat/threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
async def send_message(
    thread_id: str,
    body: MessageSend,
    session: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    svc = _service()
    async with session.begin():
        thread = await svc.get_thread(session, thread_id=thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        reply = await svc.send(
            session,
            thread_id=thread_id,
            message=body.message,
            user_id=body.user_id,
            company_name=body.company_name,
        )
    return MessageResponse.model_validate(reply)
