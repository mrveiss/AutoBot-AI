# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Per-user scoping on the legacy broadcast endpoint (review finding, #14814).

Making delivery additive so several clients could receive events fixed the
delivery bug but widened an existing leak: ``/ws`` has no channel scoping, so
every connected client would have seen every ``PersistStrategy.NONE`` event —
including other users' sessions. Previously only the single most-recently
connected client had that view; now it would have been all of them.

These pin the scoping rules, including the one that matters most: an event whose
ownership cannot be resolved is WITHHELD, not shown to whoever happens to ask.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.websockets import _event_is_for_user


class _Manager:
    def __init__(self, owners: dict):
        self._owners = owners

    async def get_session_owner(self, session_id: str):
        return self._owners.get(session_id)


def _with_manager(manager):
    return patch(
        "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
        return_value=manager,
    )


@pytest.mark.asyncio
async def test_a_system_event_with_no_owner_fields_is_visible_to_everyone():
    # Worker health, NPU status and diagnostics carry no tenant, and hiding
    # them would break the operator dashboards that consume this endpoint.
    event = {"type": "npu_worker_status_change", "payload": {"worker": "w1"}}
    assert await _event_is_for_user(event, "u1", {}) is True


@pytest.mark.asyncio
async def test_an_event_addressed_to_another_user_is_withheld():
    event = {"type": "llm_response", "payload": {"user_id": "u2", "text": "private"}}
    assert await _event_is_for_user(event, "u1", {}) is False


@pytest.mark.asyncio
async def test_an_event_addressed_to_this_user_is_delivered():
    event = {"type": "llm_response", "payload": {"user_id": "u1"}}
    assert await _event_is_for_user(event, "u1", {}) is True


@pytest.mark.asyncio
async def test_another_users_session_event_is_withheld():
    event = {"type": "tool_output", "payload": {"session_id": "s-bob"}}
    with _with_manager(_Manager({"s-bob": "bob"})):
        assert await _event_is_for_user(event, "alice", {}) is False


@pytest.mark.asyncio
async def test_your_own_session_event_is_delivered():
    event = {"type": "tool_output", "payload": {"session_id": "s-alice"}}
    with _with_manager(_Manager({"s-alice": "alice"})):
        assert await _event_is_for_user(event, "alice", {}) is True


@pytest.mark.asyncio
async def test_an_unowned_session_is_withheld_unless_its_type_is_declared():
    """#17428 owner ruling: this REVERSES the previous behaviour, deliberately.

    This test read `is True` and was commented "sessions created before
    ownership tracking have no owner recorded; hiding them would silently blank
    existing users' history". That reasoning was sound and it is what made the
    endpoint fail OPEN: an unresolvable owner meant "show it to everyone", so
    any event whose session could not be resolved went to every connected
    client. The ruling inverts the default and declares the genuinely-global
    types instead, so the old case is now the withheld one.
    """
    event = {"type": "tool_output", "payload": {"session_id": "s-legacy"}}
    with _with_manager(_Manager({})):
        assert await _event_is_for_user(event, "alice", {}) is False


@pytest.mark.asyncio
async def test_an_unowned_session_carrying_a_declared_type_is_still_broadcast():
    """The other half: the allowlist is what keeps operator telemetry working.

    Without this, the test above is satisfied by a guard that withholds
    everything -- which passes the security assertion and blanks the dashboards.
    """
    event = {"type": "log_message", "payload": {"session_id": "s-legacy"}}
    with _with_manager(_Manager({})):
        assert await _event_is_for_user(event, "alice", {}) is True


@pytest.mark.asyncio
async def test_an_unresolvable_owner_withholds_rather_than_leaks():
    """The load-bearing case: failure must not default to 'show it'."""
    event = {"type": "tool_output", "payload": {"session_id": "s-1"}}
    broken = AsyncMock()
    broken.get_session_owner.side_effect = RuntimeError("store unavailable")
    with _with_manager(broken):
        assert await _event_is_for_user(event, "alice", {}) is False


@pytest.mark.asyncio
async def test_no_history_manager_withholds_session_scoped_events():
    event = {"type": "tool_output", "payload": {"session_id": "s-1"}}
    with _with_manager(None):
        assert await _event_is_for_user(event, "alice", {}) is False


@pytest.mark.asyncio
async def test_the_owner_lookup_is_memoised_per_connection():
    manager = AsyncMock()
    manager.get_session_owner.return_value = "alice"
    cache: dict = {}
    event = {"type": "tool_output", "payload": {"session_id": "s-1"}}

    with _with_manager(manager):
        await _event_is_for_user(event, "alice", cache)
        await _event_is_for_user(event, "alice", cache)
        await _event_is_for_user(event, "alice", cache)

    assert manager.get_session_owner.await_count == 1, "a burst re-queried ownership per event"


@pytest.mark.asyncio
async def test_a_non_dict_payload_is_not_treated_as_owned():
    event = {"type": "raw", "payload": "just a string"}
    assert await _event_is_for_user(event, "u1", {}) is True


class TestAChatKeyedEventIsScopedToo:
    """#17428: the same rule, for the keys the publishers actually use.

    Each alias is asserted in PAIRS -- withheld from a non-owner AND delivered
    to the owner. A guard that withholds from everyone satisfies the first
    assertion and breaks the terminal, so neither half proves the fix alone.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["chat_id", "conversation_id"])
    async def test_another_users_chat_event_is_withheld(self, key):
        # Before #17428 this returned True: the payload had no `session_id`, so
        # it took the "system-wide, visible to everyone" branch. This is the
        # shape of `terminal_output`, which carries a sudo prompt and an
        # `input_type: password` marker keyed by `chat_id`.
        event = {"type": "terminal_output", "payload": {key: "c-bob", "output": "[sudo] password:"}}
        with _with_manager(_Manager({"c-bob": "bob"})):
            assert await _event_is_for_user(event, "alice", {}) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["chat_id", "conversation_id"])
    async def test_your_own_chat_event_is_still_delivered(self, key):
        """The other half: scoping must not blank the owner's own terminal."""
        event = {"type": "terminal_output", "payload": {key: "c-alice", "output": "$ ls"}}
        with _with_manager(_Manager({"c-alice": "alice"})):
            assert await _event_is_for_user(event, "alice", {}) is True

    @pytest.mark.asyncio
    async def test_a_synthetic_chat_id_is_unchanged(self):
        """`InteractiveTerminalAgent("detect_pm")` has no chat file.

        Unowned stays visible, exactly as for `session_id` -- this change adds
        aliases to the existing resolution, it does not alter what an
        unresolved owner means. Pinned so the behaviour is a decision rather
        than a side effect; whether it SHOULD stay visible is the open question
        on #17428.
        """
        event = {"type": "terminal_output", "payload": {"chat_id": "detect_pm"}}
        with _with_manager(_Manager({})):
            assert await _event_is_for_user(event, "alice", {}) is False

    @pytest.mark.asyncio
    async def test_a_terminal_session_id_is_not_treated_as_a_chat_id(self):
        """Deliberately still unscoped: it names a different namespace.

        Asserting the CURRENT behaviour rather than the desired one, so that
        wiring it to the wrong store fails this test instead of passing
        silently. It travels alongside `session_id` as a separate parameter, so
        `get_session_owner` cannot answer for it.
        """
        event = {"type": "approval", "payload": {"terminal_session_id": "t-bob"}}
        with _with_manager(_Manager({"t-bob": "bob"})):
            assert await _event_is_for_user(event, "alice", {}) is False

    @pytest.mark.asyncio
    async def test_session_id_wins_when_both_are_present(self):
        """Precedence is explicit, not incidental to dict ordering."""
        event = {"type": "tool_output", "payload": {"session_id": "s-alice", "chat_id": "c-bob"}}
        with _with_manager(_Manager({"s-alice": "alice", "c-bob": "bob"})):
            assert await _event_is_for_user(event, "alice", {}) is True


class TestTheBroadcastAllowlist:
    """#17428: the default is private and a broadcast is a declaration.

    An allowlist rather than a denylist, for the reason #17414 established: a
    denylist cannot see a type nobody has added yet, so a new scoped event
    would be public by default. Same shape as `MIRRORED_TO_GLOBAL_SUBSCRIBERS`
    (landing on #17375 for the fan-out side).
    """

    @pytest.mark.asyncio
    async def test_a_declared_type_with_no_identifier_reaches_everyone(self):
        event = {"type": "npu_worker_status_change", "payload": {"worker": "w1"}}
        assert await _event_is_for_user(event, "alice", {}) is True

    @pytest.mark.asyncio
    async def test_an_undeclared_type_with_no_identifier_is_withheld(self):
        """The disclosure this closes: `llm_response` carries no identifier at all.

        Before #17428 this returned True and the whole model reply reached every
        connected client. It is withheld now -- and because it can never be
        scoped by a resolver, giving it an owner at the publisher is tracked
        separately rather than declared a broadcast here, which would be using
        the allowlist to launder a disclosure.
        """
        event = {"type": "llm_response", "payload": {"response": "private reply"}}
        assert await _event_is_for_user(event, "alice", {}) is False

    @pytest.mark.asyncio
    async def test_the_allowlist_holds_only_tenant_free_infrastructure_types(self):
        """A positive control on the CONTENTS, not just the mechanism.

        An assertion that the guard consults an allowlist passes however wrong
        the allowlist is. This pins what is in it, so adding a tenant-carrying
        type has to change a test that says why each entry is there.
        """
        from type_defs.common import BROADCAST_EVENT_TYPES

        assert BROADCAST_EVENT_TYPES == frozenset(
            {
                "npu_worker_status_change",
                "npu.worker.removed",
                "worker_capability_report",
                "worker_task_start",
                "worker_task_end",
                "log_message",
            }
        )
