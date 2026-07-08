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
    """_rag_query returns [] when ChromaDB is unavailable.

    The source does a local ``from utils.async_chromadb_client import ...``
    inside the try block, so we simulate unavailability by temporarily removing
    the module from sys.modules so the import raises ImportError.
    """
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


# --------------------------------- LLM helper — malformed JSON


@pytest.mark.asyncio
async def test_resolve_via_llm_malformed_json(svc: CeoChatService) -> None:
    """_resolve_via_llm falls back to 'clarify' on malformed LLM output (both attempts)."""
    mock_response = MagicMock()
    mock_response.content = "NOT JSON"
    mock_response.error = None
    mock_svc = MagicMock()
    mock_svc.chat = AsyncMock(return_value=mock_response)

    with patch("llc.services.ceo_chat._llm_service_mod.get_llm_service", return_value=mock_svc):
        resolution = await svc._resolve_via_llm(
            message="hello",
            kb_chunks=[],
            company_name="ACME",
            conversation_id="t1",
        )

    assert resolution["intent"] == "clarify"
    # Friendly message — not a raw exception string.
    assert "exception" not in resolution["summary"].lower()
    assert resolution["summary"]


# --------------------------------- _extract_json parser


def test_extract_json_clean() -> None:
    raw = '{"intent":"create_task","summary":"ok","entity":{}}'
    result = CeoChatService._extract_json(raw)
    assert result["intent"] == "create_task"


def test_extract_json_think_block_stripped() -> None:
    raw = "<think>I should parse this carefully.</think>\n" '{"intent":"create_task","summary":"ok","entity":{}}'
    result = CeoChatService._extract_json(raw)
    assert result["intent"] == "create_task"


def test_extract_json_prose_wrapper() -> None:
    raw = (
        'Here is my answer:\n```json\n{"intent":"update_goal","summary":"raise target","entity":{"goal_id":"g1"}}\n```'
    )
    result = CeoChatService._extract_json(raw)
    assert result["intent"] == "update_goal"


def test_extract_json_think_plus_prose() -> None:
    """Models that emit <think> blocks AND wrap in prose are handled correctly."""
    raw = (
        "<think>Let me think step by step.</think>\n"
        "Sure! Here is the JSON:\n"
        '{"intent":"record_decision","summary":"approved","entity":{}}\n'
        "That should be all."
    )
    result = CeoChatService._extract_json(raw)
    assert result["intent"] == "record_decision"


def test_extract_json_no_object_raises() -> None:
    import pytest as _pytest

    with _pytest.raises((ValueError, Exception)):
        CeoChatService._extract_json("no json here at all")


# --------------------------------- _resolve_via_llm retry path


@pytest.mark.asyncio
async def test_resolve_via_llm_recovers_on_retry(svc: CeoChatService) -> None:
    """First response has think block + prose; second attempt returns clean JSON."""
    first = MagicMock()
    first.content = "<think>thinking…</think>\nHere you go: some prose before the JSON"
    first.error = None

    second = MagicMock()
    second.content = '{"intent":"create_task","summary":"Write Q3 report","entity":{"title":"Q3 report"}}'
    second.error = None

    mock_svc = MagicMock()
    mock_svc.chat = AsyncMock(side_effect=[first, second])

    with patch("llc.services.ceo_chat._llm_service_mod.get_llm_service", return_value=mock_svc):
        result = await svc._resolve_via_llm(
            message="Create a task to write the Q3 report",
            kb_chunks=[],
            company_name="TestCo",
            conversation_id="verify",
        )

    assert result["intent"] == "create_task"
    assert mock_svc.chat.await_count == 2


@pytest.mark.asyncio
async def test_resolve_via_llm_think_block_recovered_first_pass(svc: CeoChatService) -> None:
    """Think block on first response — parser should extract JSON without needing retry."""
    resp = MagicMock()
    resp.content = (
        "<think>I should figure out the intent.</think>"
        '{"intent":"create_task","summary":"Draft Q3 report","entity":{"title":"Q3 report"}}'
    )
    resp.error = None
    mock_svc = MagicMock()
    mock_svc.chat = AsyncMock(return_value=resp)

    with patch("llc.services.ceo_chat._llm_service_mod.get_llm_service", return_value=mock_svc):
        result = await svc._resolve_via_llm(
            message="Create a task to write the Q3 report",
            kb_chunks=[],
            company_name="TestCo",
            conversation_id="verify",
        )

    assert result["intent"] == "create_task"
    # Only one LLM call needed — parser succeeded first pass.
    assert mock_svc.chat.await_count == 1


@pytest.mark.asyncio
async def test_resolve_via_llm_unknown_intent_becomes_clarify(svc: CeoChatService) -> None:
    resp = MagicMock()
    resp.content = '{"intent":"do_something_weird","summary":"x","entity":{}}'
    resp.error = None
    mock_svc = MagicMock()
    mock_svc.chat = AsyncMock(return_value=resp)

    with patch("llc.services.ceo_chat._llm_service_mod.get_llm_service", return_value=mock_svc):
        result = await svc._resolve_via_llm(
            message="Do something weird",
            kb_chunks=[],
            company_name="Acme",
            conversation_id="t",
        )

    assert result["intent"] == "clarify"
