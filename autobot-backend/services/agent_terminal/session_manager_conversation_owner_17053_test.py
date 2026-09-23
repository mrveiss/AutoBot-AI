# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat-driven agent session belongs to its conversation's owner (#17053).

The chat workflow creates agent-terminal sessions with no caller, and every
agent-terminal route now acts only for a session's owner or an admin. If such a
session were stamped with no owner, the person chatting could no longer approve
their own agent's commands. The owner is resolved the way the chat ownership
gate resolves it: the session file first, then the grant the gate writes to
Redis alone when it hands a never-owned conversation to its first caller.
"""

from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

import autobot_shared.redis_client as redis_client_module
from security.session_ownership import SessionOwnershipValidator
from services.agent_terminal.session_manager import SessionManager
from services.command_approval_manager import AgentRole


class _ChatHistory:
    """ChatHistoryManager's owner accessor, with a recorded owner or a read failure."""

    def __init__(self, owner=None, error=None):
        self._owner, self._error = owner, error

    async def get_session_owner(self, session_id):
        if self._error:
            raise self._error
        return self._owner


@pytest.fixture
def grants(monkeypatch):
    """The Redis the chat ownership gate records its grants in."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _client(async_client=False, database="main"):
        assert (async_client, database) == (True, "main"), "must read where the gate writes"
        return redis

    monkeypatch.setattr(redis_client_module, "get_redis_client", _client)
    return redis


async def _grant(redis, conversation_id, username):
    await SessionOwnershipValidator(redis).set_session_owner(conversation_id, username)


@pytest.mark.asyncio
async def test_the_session_file_owner_is_the_record_of_truth(grants):
    await _grant(grants, "conv-1", "bob")
    manager = SessionManager(chat_history_manager=_ChatHistory(owner="alice"))

    assert await manager._conversation_owner("conv-1") == "alice"


@pytest.mark.asyncio
async def test_a_conversation_granted_on_its_first_message_is_owned_by_that_caller(grants):
    """The legacy_migration grant lives only in Redis; it must not leave the session ownerless."""
    await _grant(grants, "conv-1", "bob")

    for history in (_ChatHistory(owner=None), _ChatHistory(error=RuntimeError("file unreadable")), None):
        assert await SessionManager(chat_history_manager=history)._conversation_owner("conv-1") == "bob"


@pytest.mark.asyncio
async def test_a_conversation_nobody_owns_leaves_the_session_admin_only(grants):
    manager = SessionManager(chat_history_manager=_ChatHistory(owner=None))

    assert await manager._conversation_owner("conv-1") is None
    assert await manager._conversation_owner(None) is None


@pytest.mark.asyncio
async def test_an_unreachable_grant_store_fails_closed(monkeypatch):
    async def _no_redis(async_client=False, database="main"):
        return None

    monkeypatch.setattr(redis_client_module, "get_redis_client", _no_redis)

    assert await SessionManager(chat_history_manager=_ChatHistory(owner=None))._conversation_owner("conv-1") is None


def _creatable(manager: SessionManager) -> AsyncMock:
    """Stand in for PTY setup and approval restore; return the PTY mock to inspect the owner it got."""
    setup_pty = AsyncMock(return_value="pty-1")
    manager._setup_pty_for_session = setup_pty
    manager._restore_pending_approval = AsyncMock()
    return setup_pty


@pytest.mark.asyncio
async def test_a_chat_created_session_is_stamped_with_the_conversation_owner(grants):
    manager = SessionManager(chat_history_manager=_ChatHistory(owner="alice"))
    setup_pty = _creatable(manager)

    session = await manager.create_session(
        agent_id="chat_agent_conv-1", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv-1"
    )

    assert session.owner == "alice"
    assert setup_pty.await_args.args[2] == "alice", "the terminal WebSocket gate must see the same owner"


@pytest.mark.asyncio
async def test_an_explicit_creator_is_never_replaced(grants):
    manager = SessionManager(chat_history_manager=_ChatHistory(owner="alice"))
    _creatable(manager)

    session = await manager.create_session(
        agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv-1", owner="carol"
    )

    assert session.owner == "carol"


@pytest.mark.asyncio
async def test_a_session_rebuilt_from_its_pending_approval_keeps_the_conversation_owner(grants):
    """#13478 rebuilds a vanished session; its owner must not be lost with the record."""
    manager = SessionManager(chat_history_manager=_ChatHistory(owner="alice"))
    manager._conversation_for_expired_session = AsyncMock(return_value="conv-1")

    async def _restore(session, conversation_id):
        session.pending_approval = {"command": "sudo reboot"}

    manager._restore_pending_approval = _restore

    session = await manager._rebuild_session_from_pending_approval("s-gone")

    assert session is not None and session.owner == "alice"
