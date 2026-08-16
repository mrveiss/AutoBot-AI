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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat import _build_llm_context, _generate_ai_stack_chat_response, _to_persisted_message


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
