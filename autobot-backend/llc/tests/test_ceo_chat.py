# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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


# --------------------------------- send — RAG + LLM mocked


@pytest.mark.asyncio
async def test_send_clarify_intent(svc: CeoChatService) -> None:
    """send() with LLM returning 'clarify' stores no entity and returns system msg."""
    thread_id = str(uuid.uuid4())
    session = AsyncMock()
    session.flush = AsyncMock()
    # get_thread call
    thread = _make_thread()
    thread.company_id = "co1"

    with (
        patch.object(svc, "_rag_query", new=AsyncMock(return_value=[])),
        patch.object(
            svc,
            "_resolve_via_llm",
            new=AsyncMock(return_value={"intent": "clarify", "summary": "Need more info", "entity": {}}),
        ),
        patch.object(svc, "get_thread", new=AsyncMock(return_value=thread)),
    ):
        msg = await svc.send(session, thread_id=thread_id, message="hello", user_id=None)

    assert msg.author_type == "system"
    assert "clarify" in msg.body.lower() or "could you" in msg.body.lower()
    # Two flush calls: one for human_msg, one for system_msg
    assert session.flush.await_count == 2


@pytest.mark.asyncio
async def test_send_create_task_intent(svc: CeoChatService) -> None:
    """send() with 'create_task' intent delegates to WorkItemService."""
    thread_id = str(uuid.uuid4())
    thread = _make_thread()
    thread.company_id = "co1"

    fake_item = MagicMock()
    fake_item.id = uuid.uuid4()

    session = AsyncMock()
    session.flush = AsyncMock()

    with (
        patch.object(svc, "_rag_query", new=AsyncMock(return_value=["some context"])),
        patch.object(
            svc,
            "_resolve_via_llm",
            new=AsyncMock(
                return_value={
                    "intent": "create_task",
                    "summary": "Create Q3 roadmap task",
                    "entity": {"title": "Q3 Roadmap"},
                }
            ),
        ),
        patch.object(svc, "get_thread", new=AsyncMock(return_value=thread)),
        patch.object(svc, "_dispatch_intent", new=AsyncMock(return_value=("work_item", fake_item.id))),
    ):
        msg = await svc.send(session, thread_id=thread_id, message="Create a Q3 roadmap task", user_id=None)

    assert msg.author_type == "system"
    assert "work_item" in msg.body or "Resolved" in msg.body


@pytest.mark.asyncio
async def test_send_record_decision_intent(svc: CeoChatService) -> None:
    """send() with 'record_decision' creates no external entity."""
    thread_id = str(uuid.uuid4())
    thread = _make_thread()
    thread.company_id = "co1"

    session = AsyncMock()
    session.flush = AsyncMock()

    with (
        patch.object(svc, "_rag_query", new=AsyncMock(return_value=[])),
        patch.object(
            svc,
            "_resolve_via_llm",
            new=AsyncMock(return_value={"intent": "record_decision", "summary": "Approved budget", "entity": {}}),
        ),
        patch.object(svc, "get_thread", new=AsyncMock(return_value=thread)),
    ):
        msg = await svc.send(session, thread_id=thread_id, message="We approved the budget", user_id=None)

    assert msg.author_type == "system"
    assert "decision" in msg.body.lower() or "Recorded" in msg.body


# --------------------------------- build_reply


def test_build_reply_clarify() -> None:
    body = CeoChatService._build_reply({"intent": "clarify", "summary": "Need more info", "entity": {}}, None, None)
    assert "clarify" in body.lower() or "could you" in body.lower()


def test_build_reply_create_task_with_entity() -> None:
    eid = uuid.uuid4()
    body = CeoChatService._build_reply(
        {"intent": "create_task", "summary": "Created task", "entity": {}},
        "work_item",
        eid,
    )
    assert str(eid) in body
    assert "work_item" in body


def test_build_reply_no_entity_created() -> None:
    body = CeoChatService._build_reply(
        {"intent": "create_task", "summary": "Failed to create task", "entity": {}},
        None,
        None,
    )
    assert "no entity" in body.lower()


def test_build_reply_decision_no_entity_id() -> None:
    body = CeoChatService._build_reply(
        {"intent": "record_decision", "summary": "Approved budget", "entity": {}},
        "decision",
        None,
    )
    assert "decision" in body.lower()


# --------------------------------- RAG helper


@pytest.mark.asyncio
async def test_rag_query_graceful_failure(svc: CeoChatService) -> None:
    """_rag_query returns [] when ChromaDB is unavailable."""
    with patch(
        "llc.services.ceo_chat.get_async_chromadb_client",  # noqa: F821 — may not be importable in test env
        side_effect=ImportError("chromadb not available"),
        create=True,
    ):
        result = await svc._rag_query("thread_id", "query text")
    assert result == []


# --------------------------------- LLM helper — malformed JSON


@pytest.mark.asyncio
async def test_resolve_via_llm_malformed_json(svc: CeoChatService) -> None:
    """_resolve_via_llm falls back to 'clarify' on malformed LLM output."""
    mock_response = MagicMock()
    mock_response.content = "NOT JSON"
    mock_svc = MagicMock()
    mock_svc.chat = AsyncMock(return_value=mock_response)

    with patch("llc.services.ceo_chat.get_llm_service", return_value=mock_svc, create=True):
        resolution = await svc._resolve_via_llm(
            message="hello",
            kb_chunks=[],
            company_name="ACME",
            conversation_id="t1",
        )

    assert resolution["intent"] == "clarify"
