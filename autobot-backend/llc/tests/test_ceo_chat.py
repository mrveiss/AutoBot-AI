# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for CeoChatService and CEO Chat API routes (GH#8233)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.ceo_chat import LLCCeoChatMessage, LLCCeoChatThread
from llc.services.ceo_chat import CeoChatService

# ----------------------------------------------------------------- Helpers


def _make_thread(
    company_id: str = "co1",
    title: str = "Test Thread",
    resolved_entity_type: str | None = None,
    resolved_entity_id: uuid.UUID | None = None,
) -> LLCCeoChatThread:
    t = LLCCeoChatThread(
        company_id=company_id,
        title=title,
        resolved_entity_type=resolved_entity_type,
        resolved_entity_id=resolved_entity_id,
    )
    t.id = uuid.uuid4()
    t.created_at = datetime.now(tz=timezone.utc)
    t.updated_at = datetime.now(tz=timezone.utc)
    t.messages = []
    return t


def _make_message(
    thread_id: uuid.UUID | None = None,
    author_type: str = "human",
    body: str = "Hello",
) -> LLCCeoChatMessage:
    m = LLCCeoChatMessage(
        thread_id=thread_id or uuid.uuid4(),
        author_type=author_type,
        body=body,
    )
    m.id = uuid.uuid4()
    m.created_at = datetime.now(tz=timezone.utc)
    return m


# --------------------------------------------------------------- Service


@pytest.fixture
def svc() -> CeoChatService:
    return CeoChatService()


@pytest.mark.asyncio
async def test_create_thread(svc: CeoChatService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()

    thread = await svc.create_thread(session, company_id="co1", title="Board Session")

    assert thread.company_id == "co1"
    assert thread.title == "Board Session"
    session.add.assert_called_once_with(thread)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_thread_with_user(svc: CeoChatService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    user_id = str(uuid.uuid4())

    thread = await svc.create_thread(session, company_id="co1", title="Board Session", created_by_user_id=user_id)

    assert str(thread.created_by_user_id) == user_id


@pytest.mark.asyncio
async def test_get_thread_found(svc: CeoChatService) -> None:
    thread = _make_thread()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = thread
    session.execute = AsyncMock(return_value=result_mock)

    found = await svc.get_thread(session, thread_id=str(thread.id))
    assert found is thread


@pytest.mark.asyncio
async def test_get_thread_not_found(svc: CeoChatService) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    found = await svc.get_thread(session, thread_id=str(uuid.uuid4()))
    assert found is None


@pytest.mark.asyncio
async def test_list_threads(svc: CeoChatService) -> None:
    threads = [_make_thread(title=f"T{i}") for i in range(3)]
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = threads
    session.execute = AsyncMock(return_value=result_mock)

    found = await svc.list_threads(session, company_id="co1")
    assert len(found) == 3


# --------------------------------- send — delegates to the chat pipeline (#11501 T2)


class _Msg:
    """Minimal stand-in for a WorkflowMessage from the pipeline stream."""

    def __init__(self, type="response", content="", metadata=None):
        self.type = type
        self.content = content
        self.metadata = metadata or {}


@pytest.mark.asyncio
async def test_send_delegates_to_pipeline_and_persists(svc: CeoChatService) -> None:
    """send() persists the human msg, delegates to _run_pipeline, and persists
    the pipeline reply as the system message; updates thread on entity."""
    thread_id = str(uuid.uuid4())
    thread = _make_thread()
    thread.company_id = "co1"
    session = AsyncMock()
    session.flush = AsyncMock()
    with (
        patch.object(svc, "_rag_query", new=AsyncMock(return_value=[])),
        patch.object(svc, "_query_decisions", new=AsyncMock(return_value=[])),
        patch.object(svc, "get_thread", new=AsyncMock(return_value=thread)),
        patch.object(svc, "_run_pipeline", new=AsyncMock(return_value=("Created the task.", "work_item", "wi-1"))),
    ):
        msg = await svc.send(session, thread_id=thread_id, message="Create a Q3 task", user_id="u1")
    assert msg.author_type == "system"
    assert msg.body == "Created the task."
    assert session.flush.await_count == 2  # human + system
    session.execute.assert_awaited()  # thread resolution updated (entity present)


@pytest.mark.asyncio
async def test_send_no_entity_skips_thread_update(svc: CeoChatService) -> None:
    thread_id = str(uuid.uuid4())
    thread = _make_thread()
    thread.company_id = "co1"
    session = AsyncMock()
    session.flush = AsyncMock()
    with (
        patch.object(svc, "_rag_query", new=AsyncMock(return_value=[])),
        patch.object(svc, "_query_decisions", new=AsyncMock(return_value=[])),
        patch.object(svc, "get_thread", new=AsyncMock(return_value=thread)),
        patch.object(svc, "_run_pipeline", new=AsyncMock(return_value=("Here's some info.", None, None))),
    ):
        msg = await svc.send(session, thread_id=thread_id, message="what's our runway?", user_id="u1")
    assert msg.body == "Here's some info."
    session.execute.assert_not_awaited()  # no entity → no resolution update


@pytest.mark.asyncio
async def test_run_pipeline_collects_reply_and_entity(svc: CeoChatService) -> None:
    """_run_pipeline returns the last 'response' content + the LLC tool entity,
    and passes company_id/user_id in the context."""

    async def _fake_stream(session_id, message, context):
        assert context["company_id"] == "co1" and context["user_id"] == "u1"
        assert session_id == "t1"
        yield _Msg("thought", "thinking...")
        yield _Msg("command_output", "Done", {"result": {"entity_type": "work_item", "entity_id": "wi-9"}})
        yield _Msg("response", "Created the Q3 task for you.")

    fake_mgr = MagicMock()
    fake_mgr.process_message_stream = _fake_stream
    with patch("llc.services.ceo_chat._get_workflow_manager", return_value=fake_mgr):
        reply, etype, eid = await svc._run_pipeline(
            thread_id="t1", message="Create a Q3 task", company_id="co1", user_id="u1", kb_chunks=["ctx"]
        )
    assert reply == "Created the Q3 task for you."
    assert etype == "work_item" and eid == "wi-9"


@pytest.mark.asyncio
async def test_run_pipeline_default_reply_when_no_response(svc: CeoChatService) -> None:
    async def _fake_stream(session_id, message, context):
        yield _Msg("thought", "hmm")

    fake_mgr = MagicMock()
    fake_mgr.process_message_stream = _fake_stream
    with patch("llc.services.ceo_chat._get_workflow_manager", return_value=fake_mgr):
        reply, etype, eid = await svc._run_pipeline(
            thread_id="t1", message="hi", company_id="co1", user_id=None, kb_chunks=[]
        )
    assert reply == "Done." and etype is None and eid is None


# --------------------------------- _rag_query graceful failure (preserved)


@pytest.mark.asyncio
async def test_rag_query_graceful_failure(svc: CeoChatService) -> None:
    """_rag_query returns [] when ChromaDB is unavailable."""
    import sys

    sentinel = object()
    orig = sys.modules.get("utils.async_chromadb_client", sentinel)
    sys.modules["utils.async_chromadb_client"] = None  # type: ignore[assignment]
    try:
        result = await svc._rag_query("thread_id", "query text")
    finally:
        if orig is sentinel:
            sys.modules.pop("utils.async_chromadb_client", None)
        else:
            sys.modules["utils.async_chromadb_client"] = orig
    assert result == []
