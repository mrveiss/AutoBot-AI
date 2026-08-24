# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A pending approval must not die on the session's idle TTL (#13478).

#13216 reported that approvals "expire after 30 minutes". Reading the code, the
30-minute poll budget only bounds the *turn* — it never cleared the pending
approval, and `_approve_command_internal` executes on approve with no coroutine
waiting. The real expiry was one layer down and an hour later:

    session_manager.py:388   await self.redis_client.setex(key, TTL_1_HOUR, ...)

`set_pending_approval` re-persists immediately (`service.py:213`), so the clock
started when the prompt was raised and nothing refreshed it while the human
thought about it. An hour on, `get_session` missed and the approve endpoint
returned `Session not found` — the approval was unrecoverable.

The second half is subtler. `_restore_pending_approval` rebuilds the state from
chat history and is documented as surviving restarts, but it ran only inside
`create_session`, which mints a **new** session_id. The approve endpoint is
addressed by the **old** id — what the persisted approval message and the GUI
button both carry — so the restore existed and could not be reached from the one
path that needed it.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _manager():
    from services.agent_terminal.session_manager import SessionManager

    mgr = SessionManager.__new__(SessionManager)
    mgr.sessions = {}
    mgr.redis_client = AsyncMock()
    mgr.chat_history_manager = None
    import asyncio

    mgr._sessions_lock = asyncio.Lock()
    return mgr


def _session(session_id="sess-1", conversation_id="conv-1", pending=None):
    from services.agent_terminal.models import AgentSessionState, AgentTerminalSession
    from services.command_approval_manager import AgentRole

    s = AgentTerminalSession(
        session_id=session_id,
        agent_id="agent-1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id=conversation_id,
    )
    if pending:
        s.pending_approval = pending
        s.state = AgentSessionState.AWAITING_APPROVAL
    return s


def _setex_calls(mgr):
    return [c.args for c in mgr.redis_client.setex.call_args_list]


# --- D1: the TTL ------------------------------------------------------------


async def test_an_idle_session_still_expires_in_an_hour():
    """The GC this TTL exists for must keep working."""
    from constants.ttl_constants import TTL_1_HOUR

    mgr = _manager()
    await mgr._persist_session(_session())

    key, ttl, _ = _setex_calls(mgr)[0]
    assert key == "agent_terminal:session:sess-1"
    assert ttl == TTL_1_HOUR, "an abandoned session must still be collected"


async def test_a_session_awaiting_approval_gets_a_long_ttl():
    """The bug: an hour after the prompt, approving returned 'Session not found'."""
    from constants.ttl_constants import TTL_1_HOUR
    from services.agent_terminal.session_manager import APPROVAL_PENDING_SESSION_TTL

    mgr = _manager()
    await mgr._persist_session(_session(pending={"command": "ls -la"}))

    _, ttl, _ = _setex_calls(mgr)[0]
    assert ttl == APPROVAL_PENDING_SESSION_TTL
    assert ttl > TTL_1_HOUR, (
        "a session waiting on a human is not idle — the thing it waits for is a "
        "person, and an hour is well inside normal"
    )


async def test_the_persisted_payload_still_carries_the_approval():
    """A longer TTL is useless if the approval itself is not in the record."""
    mgr = _manager()
    await mgr._persist_session(_session(pending={"command": "ls -la", "risk": "HIGH"}))

    _, _, payload = _setex_calls(mgr)[0]
    assert json.loads(payload)["pending_approval"]["command"] == "ls -la"


# --- D2: reaching the restore from the approve path -------------------------


async def test_a_pending_approval_records_which_conversation_it_belongs_to():
    """`get_session` takes a session_id; the restore needs a conversation_id."""
    mgr = _manager()
    await mgr._persist_session(_session(pending={"command": "ls -la"}))

    pointers = [c for c in _setex_calls(mgr) if "approval_conversation" in c[0]]
    assert pointers, "no pointer from session_id to its conversation was written"
    key, ttl, value = pointers[0]
    assert key == "agent_terminal:approval_conversation:sess-1"
    assert value == "conv-1"
    assert ttl > 3600


async def test_no_pointer_is_written_for_a_session_without_an_approval():
    """It exists only to rescue an approval; anything else is litter."""
    mgr = _manager()
    await mgr._persist_session(_session())

    assert not [c for c in _setex_calls(mgr) if "approval_conversation" in c[0]]


async def test_an_unknown_session_id_still_returns_none():
    """The ordinary bad-id case must stay cheap and quiet."""
    mgr = _manager()
    mgr.redis_client.get = AsyncMock(return_value=None)

    assert await mgr.get_session("no-such-session") is None


async def test_a_vanished_session_is_rebuilt_from_its_unanswered_approval():
    """The path that was unreachable: approve by the OLD session id.

    Before this, `_restore_pending_approval` only ran in `create_session` and
    produced a new id, so a GUI button carrying the old one could never resolve.
    """
    mgr = _manager()
    mgr.redis_client.get = AsyncMock(side_effect=[None, b"conv-1"])
    mgr.chat_history_manager = MagicMock()

    async def _restore(session, conversation_id):
        session.pending_approval = {"command": "ls -la", "conversation_id": conversation_id}

    mgr._restore_pending_approval = _restore

    session = await mgr.get_session("sess-1")

    assert session is not None, "the approval was recoverable and was not recovered"
    assert session.session_id == "sess-1", "must keep the id the approve request used"
    assert session.get_pending_command() == "ls -la"


async def test_a_vanished_session_with_no_outstanding_approval_is_not_resurrected():
    """Only an unanswered approval justifies rebuilding a dead session."""
    mgr = _manager()
    mgr.redis_client.get = AsyncMock(side_effect=[None, b"conv-1"])
    mgr.chat_history_manager = MagicMock()

    async def _restore(session, conversation_id):
        return None  # already answered — nothing to restore

    mgr._restore_pending_approval = _restore

    assert await mgr.get_session("sess-1") is None
