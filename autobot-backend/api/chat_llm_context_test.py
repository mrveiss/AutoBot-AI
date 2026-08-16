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

from unittest.mock import MagicMock

import pytest

from api.chat import _build_llm_context, _to_persisted_message


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


class TestTheApiShapeStillWorks:
    """Both schemas reach this function; fixing one must not break the other."""

    def test_records_already_in_api_shape_pass_through(self):
        history = [{"role": "assistant", "content": "from the api"}]

        context = _build_llm_context(history, _incoming(), _manager(), None)

        assert context[0] == {"role": "assistant", "content": "from the api"}


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
