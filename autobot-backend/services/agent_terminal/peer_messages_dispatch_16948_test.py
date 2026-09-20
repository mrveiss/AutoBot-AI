# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SESSION peer messages are drained at the real dispatch seam (#16948).

`AgentTerminalService.execute_command` is the one entry point both real
callers share (the chat-tool builtin and the direct HTTP route) -- drives
`_drain_peer_messages` directly against a real `AgentTerminalSession`.
"""

from unittest.mock import AsyncMock

import pytest

from autobot_shared.status_enums import CommandRisk
from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from protocols.peer_inbox import PeerInboxDirectory, PeerMessageEntry
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio


def _session(*, session_id: str = "term-16948", tenant_id: str | None = "tenant-x") -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id=session_id,
        agent_id="agent-16948",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv-16948",
        tenant_id=tenant_id,
    )


def _sender(name: str = "rag", tenant_id: str | None = "tenant-x") -> AgentIdentity:
    return AgentIdentity(agent_id=name, agent_type=name, kind=AgentKind.AI_STACK, name=name, tenant_id=tenant_id)


def _service() -> AgentTerminalService:
    return AgentTerminalService.__new__(AgentTerminalService)


def _directory_with(session: AgentTerminalSession) -> PeerInboxDirectory:
    presence = AgentPresenceRegistry(ttl_seconds=60)
    presence.report(
        kind=AgentKind.SESSION,
        tenant_id=session.tenant_id,
        name=session.session_id,
        instance_id=session.session_id,
        busy=False,
    )
    return PeerInboxDirectory(presence)


class TestDrainPeerMessages:
    async def test_a_queued_message_is_drained_into_session_metadata(self, monkeypatch):
        session = _session()
        directory = _directory_with(session)
        directory.send(kind=AgentKind.SESSION, name=session.session_id, sender=_sender(), content="hi", message_id="m1")
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        _service()._drain_peer_messages(session)

        assert session.metadata["peer_messages"][0]["content"] == "hi"
        assert session.metadata["peer_messages"][0]["sender_name"] == "rag"

    async def test_no_pending_message_leaves_metadata_untouched(self, monkeypatch):
        session = _session()
        directory = _directory_with(session)
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        _service()._drain_peer_messages(session)

        assert "peer_messages" not in session.metadata

    async def test_a_message_arriving_after_this_drain_is_held_for_the_next_one(self, monkeypatch):
        """#16948 AC4: mid-task arrival is not handled until the next turn boundary."""
        session = _session()
        directory = _directory_with(session)
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)
        service = _service()

        service._drain_peer_messages(session)  # nothing queued yet
        assert "peer_messages" not in session.metadata

        directory.send(
            kind=AgentKind.SESSION, name=session.session_id, sender=_sender(), content="late", message_id="m2"
        )
        assert "peer_messages" not in session.metadata  # not retroactive

        service._drain_peer_messages(session)  # the next command's own boundary
        assert session.metadata["peer_messages"][0]["content"] == "late"

    async def test_a_session_with_no_real_tenant_uses_the_unknown_tenant_key(self, monkeypatch):
        """Must match sync_session_presence's own derivation exactly, or a
        send() authorized through presence would key into an inbox this
        drain call never looks under."""
        from protocols.agent_presence import UNKNOWN_TENANT

        session = _session(tenant_id=None)
        presence = AgentPresenceRegistry(ttl_seconds=60)
        directory = PeerInboxDirectory(presence)
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        # Deliver straight into the UNKNOWN_TENANT-keyed inbox, bypassing
        # send()'s own authorization (a None-tenant session is never
        # addressable through it -- this test is about the KEY matching,
        # not about whether such a session should be reachable at all).
        directory.inbox_for(kind=AgentKind.SESSION, tenant_id=UNKNOWN_TENANT, name=session.session_id).deliver(
            PeerMessageEntry(message_id="m3", sender=_sender(tenant_id=None), content="unknown-tenant-msg")
        )

        _service()._drain_peer_messages(session)

        assert session.metadata["peer_messages"][0]["content"] == "unknown-tenant-msg"


class TestExecuteCommandReachesTheDrain:
    async def test_a_real_execute_command_call_drains_a_queued_message(self, monkeypatch):
        """Drives execute_command itself, not _drain_peer_messages in isolation --
        mocks only the gates around it, matching post_execution_failure_15073_test.py's
        own _auto_execute pattern."""
        session = _session()
        directory = _directory_with(session)
        directory.send(kind=AgentKind.SESSION, name=session.session_id, sender=_sender(), content="hi", message_id="m1")
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        svc = _service()
        svc.get_session = AsyncMock(return_value=session)
        svc._assess_command = lambda command: (None, CommandRisk.SAFE, [], False, [])
        svc._check_agent_permission = lambda *_a, **_k: None
        svc._check_auto_approval_or_queue = AsyncMock(return_value=(False, {"status": "queued"}))

        await svc.execute_command(session_id=session.session_id, command="echo hi")

        assert session.metadata["peer_messages"][0]["content"] == "hi"
