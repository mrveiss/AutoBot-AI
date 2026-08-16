# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a session reset actually does (#14306).

The reported defect was that `keep_system_prompt` preserved nothing, because the
filter compared the API-shape role key against records the store keeps under
`sender`. Resolving that mismatch would have been wrong: **nothing persists a
system prompt into a session.** The only writers using that speaker are
operational notices and overflow summaries, so a "fixed" filter would preserve
"Command approved" as though it were the prompt.

The flag is vestigial — deprecation is #14359 — and the filter is deliberately
left matching the API shape, with a test below pinning that choice so a future
reader does not "fix" it back.

What was genuinely broken is that the reset **never ran**: the store call was
unawaited, and the clearing method did not exist. Both defaults are on, so the
default reset raised into a generic handler on every request.

The tests build their records with the **real writer**, and the manager mock is
async — a sync mock is exactly what let an unawaited coroutine look correct.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.chat_sessions import _clear_and_restore_session, _preserve_system_messages, _to_persisted_system_message


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
    """`get_session` is `async def` in production.

    Mocking it synchronously is what let a missing `await` survive here: the
    unawaited coroutine failed the membership test, the bare `except` swallowed
    it, and the function returned an empty list — so the reader looked fixed
    while being unreachable. The mock must be async or it tests nothing.
    """
    manager = MagicMock()
    manager.get_session = AsyncMock(return_value={"messages": messages})
    manager.update_session = AsyncMock(return_value=True)
    manager.add_messages_batch = AsyncMock(return_value=None)
    return manager


@pytest.mark.asyncio
class TestOperationalNoticesAreNotMistakenForThePrompt:
    """Pins the choice NOT to resolve the schema mismatch here (#14359).

    Reading the stored speaker would look like the obvious fix and would make
    the default reset preserve command-approval and cancellation notices as
    though they were the system prompt. Nothing writes an actual prompt into a
    session, so there is no prompt for the "fix" to find — only notices.
    """

    async def test_a_command_approval_notice_is_not_preserved(self):
        session = [_stored("system", "Command approved and executed: `ls -la`")]

        assert await _preserve_system_messages(_manager(session), "s-1") == []

    async def test_conversation_turns_are_not_preserved_either(self):
        session = [_stored("user", "deploy it"), _stored("assistant", "done")]

        assert await _preserve_system_messages(_manager(session), "s-1") == []

    async def test_an_api_shape_system_record_still_matches(self):
        """The one shape this is meant to catch. If a writer ever persists a
        real prompt in API shape, this is the path that would carry it."""
        session = [{"role": "system", "content": "You are a deployment assistant."}]

        assert len(await _preserve_system_messages(_manager(session), "s-1")) == 1

    @pytest.mark.parametrize("junk", [None, "a string", 42])
    async def test_a_malformed_record_does_not_break_the_reset(self, junk):
        session = [junk, {"role": "system", "content": "prompt"}]

        assert len(await _preserve_system_messages(_manager(session), "s-1")) == 1

    async def test_a_store_that_raises_preserves_nothing_rather_than_failing(self):
        manager = MagicMock()
        manager.get_session = AsyncMock(side_effect=RuntimeError("store down"))

        assert await _preserve_system_messages(manager, "s-1") == []


@pytest.mark.asyncio
class TestWhateverIsKeptSurvivesWithItsText:
    """Finding it is only half — it is then translated back for writing.

    #7025 asserted its source hands over API-shape records. Reading the body
    through the normaliser means a stored-shape record is not written back with
    an empty one, whichever shape actually arrives.
    """

    async def test_a_stored_shape_record_keeps_its_body(self):
        persisted = _to_persisted_system_message(_stored("system", "You are a deployment assistant."))

        assert persisted["content"] == "You are a deployment assistant."
        assert persisted["sender"] == "system"

    async def test_an_api_shape_record_round_trips_too(self):
        persisted = _to_persisted_system_message({"role": "system", "content": "from the api"})

        assert persisted["content"] == "from the api"
        assert persisted["sender"] == "system"


@pytest.mark.asyncio
class TestTheResetItselfRuns:
    """The preserve step is the second hop; the reset has to survive the first.

    `_clear_and_restore_session` called a method the manager does not have. Both
    request flags default to on, so the DEFAULT reset raised `AttributeError`
    into the endpoint's generic handler — the preserved prompt could never have
    been written back, whatever the filter returned.

    Untested until now, which is why a wrong method name survived. These call the
    real helper against a manager that only answers what the store really
    implements.
    """

    async def test_a_reset_clears_the_session_without_deleting_it(self):
        manager = _manager([])

        await _clear_and_restore_session(manager, "s-1", [])

        manager.update_session.assert_awaited_once_with("s-1", {"messages": []})
        assert not manager.delete_session.called, "clearing must not destroy the session record"

    async def test_the_preserved_prompt_is_written_back(self):
        manager = _manager([])
        keep = [_stored("system", "You are a deployment assistant.")]

        restored = await _clear_and_restore_session(manager, "s-1", keep)

        assert restored == 1
        session_id, written = manager.add_messages_batch.await_args.args
        assert session_id == "s-1"
        assert written[0]["content"] == "You are a deployment assistant."

    async def test_a_manager_missing_the_clearing_method_fails_loudly(self):
        """The bug was a silent wrong name. If the store ever drops this method,
        that must surface here rather than in a swallowed exception."""
        manager = MagicMock(spec=["add_messages_batch"])

        with pytest.raises(AttributeError):
            await _clear_and_restore_session(manager, "s-1", [])
