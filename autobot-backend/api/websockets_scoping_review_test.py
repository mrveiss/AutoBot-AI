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
async def test_an_unowned_session_stays_visible():
    # Sessions created before ownership tracking have no owner recorded;
    # hiding them would silently blank existing users' history.
    event = {"type": "tool_output", "payload": {"session_id": "s-legacy"}}
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
