# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Translation from AutoBot workflow messages to ACP updates (#14825).

The runner is the seam between AutoBot's own message vocabulary and ACP's, which
is what keeps the protocol layer testable without an LLM and keeps the chat
workflow free of ACP vocabulary.

The case worth guarding is the unknown message type: it must still reach the
user as reply text. Dropping it would make an editor silently show nothing for
output AutoBot did produce — a failure the user cannot distinguish from the
agent having no answer.
"""

from typing import Any, AsyncIterator, Dict, List
from unittest.mock import patch

import pytest

from acp import runner as runner_module
from acp.runner import _text_of, autobot_turn_runner


class _FakeManager:
    """Yields a scripted message stream in place of the chat workflow."""

    def __init__(self, messages: List[Dict[str, Any]]):
        self._messages = messages
        self.seen_context: Dict[str, Any] | None = None

    async def initialize(self) -> None:
        return None

    async def process_message_stream(
        self, session_id: str, message: str, context: Dict[str, Any] | None = None
    ) -> AsyncIterator[Dict[str, Any]]:
        self.seen_context = context
        for m in self._messages:
            yield m


async def _collect(messages: List[Dict[str, Any]], cwd: str = "/work") -> List[Dict[str, Any]]:
    manager = _FakeManager(messages)
    runner_module._manager = manager
    return [u async for u in autobot_turn_runner("s-1", "do it", cwd)]


@pytest.fixture(autouse=True)
def reset_manager():
    yield
    runner_module._manager = None


def test_text_of_prefers_text_then_falls_back():
    assert _text_of({"text": "a", "content": "b"}) == "a"
    assert _text_of({"content": "b"}) == "b"
    assert _text_of({"chunk": "c"}) == "c"
    assert _text_of({}) == ""


def test_text_of_ignores_non_string_values():
    # A dict under `content` must not be stringified into the prompt.
    assert _text_of({"content": {"nested": 1}, "text": "real"}) == "real"


@pytest.mark.asyncio
async def test_a_reply_becomes_an_agent_message_chunk():
    updates = await _collect([{"type": "llm_response", "text": "the answer"}])

    assert len(updates) == 1
    assert updates[0]["update"]["sessionUpdate"] == "agent_message_chunk"
    assert updates[0]["update"]["content"]["text"] == "the answer"


@pytest.mark.asyncio
async def test_reasoning_becomes_a_thought_chunk_not_a_reply():
    updates = await _collect([{"type": "thought", "text": "thinking"}])

    assert updates[0]["update"]["sessionUpdate"] == "agent_thought_chunk"


@pytest.mark.asyncio
async def test_tool_activity_becomes_a_tool_call_update():
    updates = await _collect([{"type": "agent_tool_call", "text": "ls", "tool_name": "shell"}])

    assert updates[0]["update"]["sessionUpdate"] == "tool_call"
    assert updates[0]["update"]["title"] == "shell"


@pytest.mark.asyncio
async def test_a_tool_result_is_reported_as_completed():
    updates = await _collect([{"type": "agent_tool_result", "text": "done", "tool_name": "shell"}])

    assert updates[0]["update"]["status"] == "completed"


@pytest.mark.asyncio
async def test_an_unknown_type_still_reaches_the_user_as_reply_text():
    # Silence would be indistinguishable from the agent having no answer.
    updates = await _collect([{"type": "something_new", "text": "surprise output"}])

    assert len(updates) == 1
    assert updates[0]["update"]["content"]["text"] == "surprise output"


@pytest.mark.asyncio
async def test_messages_with_no_text_are_skipped():
    updates = await _collect([{"type": "llm_response"}, {"type": "llm_response", "text": "kept"}])

    assert len(updates) == 1
    assert updates[0]["update"]["content"]["text"] == "kept"


@pytest.mark.asyncio
async def test_non_dict_messages_are_skipped():
    updates = await _collect(["not a dict", {"type": "llm_response", "text": "kept"}])

    assert len(updates) == 1


@pytest.mark.asyncio
async def test_the_working_directory_reaches_the_workflow_context():
    manager = _FakeManager([{"type": "llm_response", "text": "x"}])
    runner_module._manager = manager

    [_ async for _ in autobot_turn_runner("s-1", "do it", "/repo/root")]

    assert manager.seen_context is not None
    assert manager.seen_context["cwd"] == "/repo/root"
    assert manager.seen_context["source"] == "acp"


@pytest.mark.asyncio
async def test_an_unavailable_workflow_reports_to_the_client_rather_than_crashing():
    """An editor must be told why nothing happened; a bare exception would
    surface as a dead session with no explanation."""
    runner_module._manager = None
    with patch.dict("sys.modules", {"chat_workflow": None}):
        updates = [u async for u in autobot_turn_runner("s-1", "hi", "/work")]

    assert len(updates) == 1
    assert "unavailable" in updates[0]["update"]["content"]["text"].lower()
