# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An attached file's text reaches the provider's HTTP body (#20195).

``attachment_context_20195_test.py`` stops at ``llm_params["prompt"]``. This one drives the graph's own nodes,
``prepare_llm`` then ``_run_llm_iteration``, against the real file manager and a recording HTTP connection, and
reads what was actually posted. Only the connection (and the file-manager lookup) are doubles.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from autobot_shared.ai_lines import VERIFIED_ATTACHMENT_ACCESS_KEY, VERIFIED_USER_KEY
from chat_workflow import graph
from chat_workflow.manager import ChatWorkflowManager
from conversation_file_manager import ConversationFileManager
from testkit.fake_http_client import FakeHttpClient, FakeReply, FakeStreamBody, ollama_chunk

_FACT = "quarterly-figure-4242"
_BASE = "BASE PROMPT"
_ALICE = "s-alice"
_BOB_SESSION = "s-bob"


@pytest.fixture
def world(tmp_path, monkeypatch):
    files = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    files._initialize_schema()
    monkeypatch.setattr(files, "_get_redis_sessions", AsyncMock(side_effect=RedisConnectionError("down")))

    async def _get():
        return files

    monkeypatch.setattr("conversation_file_manager.get_conversation_file_manager", _get)

    http = FakeHttpClient(FakeReply(200, FakeStreamBody([ollama_chunk("done", done=True)])))
    monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: http)

    chat = ChatWorkflowManager.__new__(ChatWorkflowManager)
    chat._register_user_message_in_history = MagicMock()
    chat._prepare_llm_request_params = AsyncMock(
        side_effect=lambda *a, **k: {"prompt": _BASE, "model": "m", "endpoint": "http://provider/api/generate"}
    )
    chat.get_or_create_session = AsyncMock(
        return_value=SimpleNamespace(session_id=_ALICE, metadata={}, conversation_history=[])
    )
    return SimpleNamespace(chat=chat, files=files, http=http)


async def _seed(w, session, name, body: bytes, user="alice") -> str:
    stored = await w.files.add_file(session, body, name, mime_type="text/plain", uploaded_by=user)
    return stored["file_id"]


async def _posted_bodies(w, ids, *, authorized=True):
    """One turn through ``prepare_llm`` then ``_run_llm_iteration``; the JSON bodies the provider was sent."""
    context = {"attachments": ids, VERIFIED_USER_KEY: "alice"}
    if authorized:
        context[VERIFIED_ATTACHMENT_ACCESS_KEY] = True
    state = {"session_id": _ALICE, "terminal_session_id": "t1", "user_message": "what does the file say?"}
    state["context"] = context
    config = {"configurable": {"manager": w.chat, "stream_callback": None}}
    update = await graph.prepare_llm(state, config)
    state.update(update)
    ctx = graph._build_llm_iteration_context(state)
    await graph._run_llm_iteration(w.chat, ctx, 1, [], None)
    return w.http.posts


def _text(body) -> str:
    return json.dumps(body)


@pytest.mark.asyncio
async def test_an_attached_files_text_is_in_the_body_posted_to_the_provider(world):
    file_id = await _seed(world, _ALICE, "report.txt", f"Revenue: {_FACT}\n".encode())
    posts = await _posted_bodies(world, [file_id])
    assert len(posts) == 1
    sent = _text(posts[0])
    assert _FACT in sent and "Attached files" in sent
    assert sent.index(_FACT) < sent.rindex(_BASE)  # the block leads; the base prompt follows it


@pytest.mark.asyncio
async def test_control_another_sessions_file_never_reaches_the_provider(world):
    bobs = await _seed(world, _BOB_SESSION, "bob.txt", f"bob private {_FACT}".encode(), user="bob")
    posts = await _posted_bodies(world, [bobs])
    assert len(posts) == 1
    assert _FACT not in _text(posts[0])


@pytest.mark.asyncio
async def test_control_without_the_strict_verdict_nothing_is_read(world):
    file_id = await _seed(world, _ALICE, "report.txt", f"Revenue: {_FACT}\n".encode())
    posts = await _posted_bodies(world, [file_id], authorized=False)
    assert len(posts) == 1
    assert _FACT not in _text(posts[0])


@pytest.mark.asyncio
async def test_control_a_turn_with_no_attachments_has_no_attached_files_header(world):
    posts = await _posted_bodies(world, [])
    assert len(posts) == 1
    assert "Attached files" not in _text(posts[0]) and _BASE in _text(posts[0])
