# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What `_build_llm_context` hands the model (#14305).

It mapped the role key with a caller-shaped default over records that
`_to_persisted_message` — in the same file — stores the speaker under `sender`.
The key was therefore always absent, and **every** prior turn reached the model
attributed to the caller, the assistant's own replies included.

The body survived only because that writer happens to name its field the same as
the API does. The speaker did not survive at all.

Nothing caught it because the two existing tests
(`api/chat_test.py`, `tests/unit/chat_workflow/test_citations_default_on.py`)
both patch `_build_llm_context` out with `return_value=[]` — they mock the
function rather than exercise its mapping. So these tests build their records
with the **real writer** and call the **real function**.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat import _build_llm_context, _generate_ai_stack_chat_response, _to_persisted_message
from api.websockets import NON_CONVERSATIONAL_WEBSOCKET_MESSAGE_TYPES, _create_broadcast_event_handler
from chat_history.messages import MessagesMixin


def _persisted(role: str, content: str) -> dict:
    """A record in the shape the chat API actually stores.

    Built by the real writer rather than hand-written — a hand-written record is
    what let this defect survive, since it would have carried the very key the
    reader was looking for.
    """
    return _to_persisted_message(
        {"id": f"m-{role}-{abs(hash(content)) % 10_000}", "role": role, "content": content},
        "message" if role == "user" else "response",
    )


def _manager(limit: int = 20):
    manager = MagicMock()
    manager.context_manager.get_message_limit = MagicMock(return_value=limit)
    return manager


def _incoming(text: str = "and now?"):
    message = MagicMock()
    message.role = "user"
    message.content = text
    return message


class TestTheSpeakerSurvives:
    """The defect: the assistant's own words came back as the caller's."""

    def test_an_assistant_turn_is_not_attributed_to_the_caller(self):
        history = [_persisted("user", "deploy it"), _persisted("assistant", "running code-sync")]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert [m["role"] for m in context[:2]] == ["user", "assistant"]

    def test_the_writer_really_does_store_the_speaker_elsewhere(self):
        """Precondition, so this test cannot pass by the bug being absent for
        some other reason."""
        stored = _persisted("assistant", "hi")

        assert "role" not in stored, "the writer stores the speaker under a different key"
        assert stored["sender"] == "assistant"

    def test_the_bodies_are_carried_through_unchanged(self):
        history = [_persisted("user", "deploy it"), _persisted("assistant", "running code-sync")]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert [m["content"] for m in context[:2]] == ["deploy it", "running code-sync"]


class TestSpeakersThatAreNotConversationalRoles:
    """A session is not written only by the chat turn.

    Terminal integration, the agent terminal and the workflow state machine
    persist into the *same* session under speakers of their own. Reading the
    speaker faithfully and forwarding it builds a request the provider rejects,
    which fails the whole turn — strictly worse than the mislabelling this fix
    is about. So the LLM reader clamps.
    """

    @pytest.mark.parametrize("speaker", ["terminal", "agent_terminal", "main-backend"])
    def test_a_non_conversational_speaker_never_reaches_the_provider(self, speaker):
        history = [{"sender": speaker, "text": "$ ls -la", "messageType": "terminal_output"}]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert {m["role"] for m in context} <= {"user", "assistant"}

    def test_the_body_of_such_a_record_is_still_carried(self):
        """Clamping the speaker must not also drop the turn — terminal output
        is context the model legitimately needs."""
        history = [{"sender": "terminal", "text": "$ ls -la", "messageType": "terminal_output"}]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert context[0]["content"] == "$ ls -la"

    def test_a_stored_system_notice_does_not_become_a_system_turn(self):
        """The approval handler persists under that speaker. An adapter that
        splits the system role out overwrites the system prompt with whatever
        it finds, so passing this through would replace the real instructions."""
        history = [{"sender": "system", "text": "Command approved"}]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert context[0]["role"] != "system"


class TestTheApiShapeStillWorks:
    """Both schemas reach this function; fixing one must not break the other."""

    def test_records_already_in_api_shape_pass_through(self):
        history = [{"role": "assistant", "content": "from the api"}]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert context[0] == {"role": "assistant", "content": "from the api"}


class TestTheAiStackPathCarriedTheSameDefect:
    """`_generate_ai_stack_chat_response` builds its history from the same
    store, in the same stored shape — so it mislabelled every turn identically.

    Found by review of this change: fixing one reader in a file that holds two
    leaves the second one live.
    """

    @pytest.mark.asyncio
    async def test_an_assistant_turn_is_not_attributed_to_the_caller(self):
        client = MagicMock()
        client.chat_message = AsyncMock(return_value={"response": "ok"})
        history = [_persisted("user", "deploy it"), _persisted("assistant", "running code-sync")]

        with patch("api.chat.get_ai_stack_client", AsyncMock(return_value=client)):
            await _generate_ai_stack_chat_response(_incoming(), history, None, _manager(), None)

        sent = client.chat_message.call_args.kwargs["chat_history"]
        assert [m["role"] for m in sent] == ["user", "assistant"]
        assert [m["content"] for m in sent] == ["deploy it", "running code-sync"]

    @pytest.mark.asyncio
    async def test_a_non_conversational_speaker_never_reaches_the_provider(self):
        client = MagicMock()
        client.chat_message = AsyncMock(return_value={"response": "ok"})
        history = [{"sender": "terminal", "text": "$ ls -la"}]

        with patch("api.chat.get_ai_stack_client", AsyncMock(return_value=client)):
            await _generate_ai_stack_chat_response(_incoming(), history, None, _manager(), None)

        sent = client.chat_message.call_args.kwargs["chat_history"]
        assert {m["role"] for m in sent} <= {"user", "assistant"}


class TestTheIncomingTurnAndLimit:
    def test_the_new_message_is_appended_last(self):
        context = _build_llm_context([_persisted("user", "old")], _incoming("brand new"), _manager(), None)

        assert context[-1] == {"role": "user", "content": "brand new"}

    def test_only_the_most_recent_history_is_included(self):
        history = [_persisted("user", f"turn {i}") for i in range(10)]

        context = _build_llm_context(history, _incoming(), _manager(limit=3), None)

        # 3 from history + the incoming turn
        assert len(context) == 4
        assert context[0]["content"] == "turn 7"

    @pytest.mark.parametrize("junk", [None, "a string", 42])
    def test_a_malformed_history_entry_does_not_break_the_turn(self, junk):
        """Malformed history is data, not a programming error — a 500 here would
        lose an answer that was already generated."""
        history = [junk, _persisted("user", "real")]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert {"role": "user", "content": "real"} in context


class _RecordingHistory(MessagesMixin):
    """Real add_message/get_session_messages pair over an in-memory store —
    used here to produce a *real* #14342-routed record, not a hand-built dict
    already shaped like the check below."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = list(messages)
        return True


class _FakeWebSocket:
    async def send_json(self, data: dict) -> None:
        pass


class TestWebsocketTelemetryPinnedDecision:
    """#14342 review follow-up: #14342 fixed *where* websocket-broadcast UI
    telemetry is stored (its own session, not a bucket no reader touched).
    That alone would have made it newly reachable from `_build_llm_context`
    as a conversational turn. The decision, pinned here: it does not enter
    `llm_context` — it is UI telemetry, not something the user or the
    assistant said.

    Built through the real #14342 producer (`broadcast_event`, the callback
    `events/bus.py` invokes) into a real session store, not a hand-fed dict
    already carrying the key the filter checks — the same trap that let
    #14340/#14341 hide.
    """

    def test_a_real_tool_output_event_does_not_enter_llm_context(self):
        manager = _RecordingHistory()

        async def seed_and_read() -> list:
            broadcast_event = await _create_broadcast_event_handler(_FakeWebSocket(), manager)
            await broadcast_event(
                {"type": "tool_output", "payload": {"output": "rm -rf leftover", "session_id": "s-1"}}
            )
            await manager.add_message(sender="user", text="clean up the workspace", session_id="s-1")
            return await manager.get_session_messages("s-1", limit=500)

        chat_context = asyncio.run(seed_and_read())
        assert len(chat_context) == 2, "precondition: both records really did land in the session"

        context = _build_llm_context(chat_context, _incoming("what did you just do?"), _manager(), None)

        assert not any("rm -rf leftover" in m["content"] for m in context)
        assert any(m["content"] == "clean up the workspace" for m in context)

    def test_the_full_dispatch_table_is_covered_minus_the_two_real_turns(self):
        """Precondition on the constant itself: guards against the allowlist
        silently shrinking to nothing (or growing to swallow real turns) as
        MESSAGE_TYPE_FORMATTERS changes."""
        from api.websockets import MESSAGE_TYPE_FORMATTERS

        assert NON_CONVERSATIONAL_WEBSOCKET_MESSAGE_TYPES == set(MESSAGE_TYPE_FORMATTERS) - {
            "user_message",
            "llm_response",
        }
        assert "tool_output" in NON_CONVERSATIONAL_WEBSOCKET_MESSAGE_TYPES
        assert "workflow_failed" in NON_CONVERSATIONAL_WEBSOCKET_MESSAGE_TYPES
        assert "user_message" not in NON_CONVERSATIONAL_WEBSOCKET_MESSAGE_TYPES

    def test_telemetry_does_not_evict_real_dialogue_from_the_window(self):
        """Window-displacement case: a burst of telemetry between two real
        turns must not push the earlier real turn out of a count-bounded
        window — filtering has to happen before the slice, not after."""
        history = (
            [_persisted("user", "turn 0")]
            + [{"sender": "workflow", "text": f"step {i}", "messageType": "workflow_step_started"} for i in range(5)]
            + [_persisted("assistant", "turn 1")]
        )

        context = _build_llm_context(history, _incoming("turn 2"), _manager(limit=2), None)

        # limit=2 conversational turns from history + the incoming turn, none
        # of them telemetry — the 5-record telemetry burst must not have
        # consumed the 2-slot budget the slice is meant to give real turns.
        assert [m["content"] for m in context] == ["turn 0", "turn 1", "turn 2"]

    @pytest.mark.asyncio
    async def test_a_real_tool_output_event_does_not_enter_the_ai_stack_history(self):
        manager = _RecordingHistory()
        broadcast_event = await _create_broadcast_event_handler(_FakeWebSocket(), manager)
        await broadcast_event({"type": "tool_output", "payload": {"output": "secret command", "session_id": "s-2"}})
        await manager.add_message(sender="user", text="deploy it", session_id="s-2")
        chat_context = await manager.get_session_messages("s-2", limit=500)

        client = MagicMock()
        client.chat_message = AsyncMock(return_value={"response": "ok"})

        with patch("api.chat.get_ai_stack_client", AsyncMock(return_value=client)):
            await _generate_ai_stack_chat_response(_incoming(), chat_context, None, _manager(), None)

        sent = client.chat_message.call_args.kwargs["chat_history"]
        assert not any("secret command" in m["content"] for m in sent)
        assert any(m["content"] == "deploy it" for m in sent)
