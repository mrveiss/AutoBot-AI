# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What survives a session reset that asked to keep the prompt (#14306).

`_preserve_system_messages` filtered on the API-shape role key against records
the session store keeps under `sender`. The comparison was never true, so the
reset preserved nothing — and reported the count it preserved as 0, which reads
as *there was no system prompt* rather than as a failure.

The flag that requests this defaults to on, so the default reset discarded it.

Nothing caught it because #7025's own docstring asserts the wrong premise —
"``_preserve_system_messages`` returns messages with ``role`` keys" — and the
downstream translator was written to match that assertion rather than the
records the source actually returns. The two agreed with each other about a
shape the store does not produce.

So these tests build their records with the **real writer** and assert on what
comes back out.
"""

from unittest.mock import MagicMock

import pytest

from api.chat_sessions import _preserve_system_messages, _to_persisted_system_message


def _stored(sender: str, text: str) -> dict:
    """A record in the shape the session store actually keeps."""
    from chat_history.messages import MessagesMixin

    return MessagesMixin._build_message_dict(
        None,
        sender=sender,
        text=text,
        message_type="chat",
        raw_data={},
        tool_markers=None,
    )


def _manager(messages):
    manager = MagicMock()
    manager.get_session = MagicMock(return_value={"messages": messages})
    return manager


class TestThePromptIsActuallyFound:
    """The defect: the filter never matched, so nothing was ever preserved."""

    def test_a_stored_system_prompt_is_preserved(self):
        session = [
            _stored("system", "You are a deployment assistant."),
            _stored("user", "deploy it"),
            _stored("assistant", "running code-sync"),
        ]

        kept = _preserve_system_messages(_manager(session), "s-1")

        assert len(kept) == 1

    def test_the_store_really_does_use_the_other_key(self):
        """Precondition, so this cannot pass by the bug being absent for some
        unrelated reason."""
        stored = _stored("system", "prompt")

        assert "role" not in stored, "the writer stores the speaker under a different key"
        assert stored["sender"] == "system"

    def test_conversation_turns_are_not_preserved(self):
        """The filter still has to filter — a reset that kept everything would
        also pass the test above."""
        session = [_stored("user", "deploy it"), _stored("assistant", "done")]

        assert _preserve_system_messages(_manager(session), "s-1") == []

    def test_records_already_in_api_shape_still_match(self):
        session = [{"role": "system", "content": "from the api"}]

        assert len(_preserve_system_messages(_manager(session), "s-1")) == 1

    @pytest.mark.parametrize("junk", [None, "a string", 42])
    def test_a_malformed_record_does_not_break_the_reset(self, junk):
        session = [junk, _stored("system", "prompt")]

        assert len(_preserve_system_messages(_manager(session), "s-1")) == 1

    def test_a_store_that_raises_preserves_nothing_rather_than_failing(self):
        manager = MagicMock()
        manager.get_session = MagicMock(side_effect=RuntimeError("store down"))

        assert _preserve_system_messages(manager, "s-1") == []


class TestThePromptSurvivesWithItsText:
    """Finding it is only half — it is then translated back for writing."""

    def test_the_body_is_carried_through_the_round_trip(self):
        session = [_stored("system", "You are a deployment assistant.")]

        kept = _preserve_system_messages(_manager(session), "s-1")
        persisted = _to_persisted_system_message(kept[0])

        assert persisted["content"] == "You are a deployment assistant."
        assert persisted["sender"] == "system"

    def test_an_api_shape_record_round_trips_too(self):
        persisted = _to_persisted_system_message({"role": "system", "content": "from the api"})

        assert persisted["content"] == "from the api"
        assert persisted["sender"] == "system"
