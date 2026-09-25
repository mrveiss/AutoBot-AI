# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A new agent-terminal session binds only a conversation its creator owns (#17422).

``POST /api/agent-terminal/sessions`` takes ``conversation_id`` from the request
body. The creator's username came from the JWT and was passed as an explicit
``owner``, which skipped the only place the conversation's owner was resolved
(#17053's ``owner is None`` branch). So any signed-in user could bind another
user's conversation, be recorded as the session's owner, and have that
conversation's pending approval restored into it -- and every #17053 check then
passed, because the record named them.

The route tests drive a real ``SessionManager`` behind the real route, so the
refusal they see is the service's check, not a stub standing in for it. Only
PTY setup and the approval restore are replaced, the latter to prove it is
never reached for a refused caller.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.agent_terminal as terminal_api
import api.agent_terminal_access as access
from constants.error_constants import ERR_SESSION_NOT_FOUND
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_ownership import SessionOwnershipValidator
from services.agent_terminal.conversation_owner import ConversationNotOwnedError
from services.agent_terminal.session_manager import SessionManager
from services.command_approval_manager import AgentRole

ALICE = {"username": "alice", "role": "user", "auth_method": "session", "org_id": "org-a"}
MALLORY = {"username": "mallory", "role": "user", "auth_method": "session", "org_id": "org-b"}
ADMIN = {"username": "root", "role": "admin", "auth_method": "session", "org_id": "org-a"}

#: conversation_id -> its recorded owner; None is a conversation nobody owns.
CONVERSATIONS = {"conv-alice": "alice", "conv-unowned": None}
#: A conversation whose session file exists but cannot be read or decrypted.
UNREADABLE = "conv-unreadable"


class _ChatHistory:
    """ChatHistoryManager's owner accessor over CONVERSATIONS."""

    async def get_session_owner(self, conversation_id):
        if conversation_id == UNREADABLE:
            raise SessionOwnerUnreadable(conversation_id)
        return CONVERSATIONS.get(conversation_id)


async def _grant(monkeypatch, conversation_id, username):
    """What the chat ownership gate writes when it hands a conversation to its caller (legacy_migration)."""
    import fakeredis.aioredis

    import autobot_shared.redis_client as redis_client_module

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await SessionOwnershipValidator(redis).set_session_owner(conversation_id, username)

    async def _client(async_client=False, database="main"):
        return redis

    monkeypatch.setattr(redis_client_module, "get_redis_client", _client)


@pytest.fixture(autouse=True)
def _no_grant_store(monkeypatch):
    """No Redis grant either, so the session file alone decides (#17053's second source)."""
    import autobot_shared.redis_client as redis_client_module

    async def _none(async_client=False, database="main"):
        return None

    monkeypatch.setattr(redis_client_module, "get_redis_client", _none)


def _manager() -> SessionManager:
    manager = SessionManager(chat_history_manager=_ChatHistory())
    manager._setup_pty_for_session = AsyncMock(return_value="pty-1")
    manager._restore_pending_approval = AsyncMock()
    return manager


@pytest.fixture
def terminal():
    manager = _manager()
    identity = SimpleNamespace(user=dict(ALICE))
    app = FastAPI()
    app.include_router(terminal_api.router, prefix="/api")
    app.dependency_overrides[access.get_current_user] = lambda: identity.user
    app.dependency_overrides[access.get_agent_terminal_service] = lambda: manager
    return SimpleNamespace(client=TestClient(app), manager=manager, identity=identity)


def _create(terminal, as_user: dict, conversation_id):
    terminal.identity.user = dict(as_user)
    body = {"agent_id": "agent-1", "agent_role": "chat_agent", "conversation_id": conversation_id}
    return terminal.client.post("/api/agent-terminal/sessions", json=body)


# --- the route --------------------------------------------------------------


@pytest.mark.parametrize(
    "as_user, conversation_id",
    [(MALLORY, "conv-alice"), (MALLORY, "conv-unowned"), (MALLORY, "conv-never-existed"), (ADMIN, "conv-alice")],
    ids=["someone-elses", "unowned", "unknown", "admin-on-someone-elses"],
)
def test_binding_a_conversation_you_do_not_own_is_404_and_nothing_is_created(terminal, as_user, conversation_id):
    response = _create(terminal, as_user, conversation_id)

    assert (
        response.status_code == 404
    ), f"{as_user['username']} bound {conversation_id}, which they do not own: {response.text}"
    assert response.json()["detail"] == ERR_SESSION_NOT_FOUND, "same answer as a missing session"
    assert terminal.manager.sessions == {}
    terminal.manager._setup_pty_for_session.assert_not_awaited()
    terminal.manager._restore_pending_approval.assert_not_awaited()


def test_the_owner_binds_their_own_conversation(terminal):
    response = _create(terminal, ALICE, "conv-alice")

    assert response.status_code == 200, response.text
    (session,) = terminal.manager.sessions.values()
    assert (session.owner, session.conversation_id, session.tenant_id) == ("alice", "conv-alice", "org-a")
    terminal.manager._restore_pending_approval.assert_awaited_once_with(session, "conv-alice")


def test_a_session_with_no_conversation_is_still_created(terminal):
    response = _create(terminal, MALLORY, None)

    assert response.status_code == 200, response.text
    (session,) = terminal.manager.sessions.values()
    assert (session.owner, session.conversation_id) == ("mallory", None)


# --- the service: no caller can skip it -------------------------------------


@pytest.mark.asyncio
async def test_an_explicit_owner_is_checked_against_the_conversation():
    manager = _manager()

    with pytest.raises(ConversationNotOwnedError, match="conv-alice"):  # mallory does not own it
        await manager.create_session(
            agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv-alice", owner="mallory"
        )

    assert manager.sessions == {}
    manager._restore_pending_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_implicit_owner_is_the_conversations_own_so_it_cannot_name_someone_else():
    """The chat workflow passes no owner: the session is stamped with the conversation's, never a caller's."""
    manager = _manager()

    session = await manager.create_session(agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv-alice")

    assert session.owner == "alice"
    manager._restore_pending_approval.assert_awaited_once_with(session, "conv-alice")


# --- an unreadable owner record is not an unowned one (review on #17426) ----


@pytest.mark.asyncio
async def test_a_grant_on_a_conversation_whose_owner_is_unreadable_is_refused(monkeypatch):
    """The chat gate grants a conversation it cannot read to its next caller; that grant proves nothing."""
    await _grant(monkeypatch, UNREADABLE, "mallory")
    manager = _manager()

    with pytest.raises(ConversationNotOwnedError, match=UNREADABLE):
        await manager.create_session(
            agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id=UNREADABLE, owner="mallory"
        )

    assert manager.sessions == {}
    manager._restore_pending_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_grant_on_a_readable_unowned_conversation_still_binds(monkeypatch):
    """A file that reads as genuinely unowned plus the gate's grant is the legitimate legacy path."""
    await _grant(monkeypatch, "conv-unowned", "mallory")
    manager = _manager()

    session = await manager.create_session(
        agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv-unowned", owner="mallory"
    )

    assert session.owner == "mallory"
