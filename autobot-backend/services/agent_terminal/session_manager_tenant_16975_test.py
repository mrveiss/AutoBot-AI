# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SessionManager.create_session threads tenant_id onto the session (#16975).

A terminal session had no tenant, and none was recoverable after the fact
(see the module docstring in protocols/agent_presence_feeds.py's
sync_session_presence). The fix is capturing it at creation, while the
authenticated principal is still in hand -- this drives create_session
itself, not a helper in isolation, so a future refactor that stops passing
tenant_id through would fail here.
"""

import fakeredis
import pytest

from services.agent_terminal.session_manager import SessionManager
from services.terminal_session_store import SessionConfigStore


@pytest.fixture(autouse=True)
def _fake_session_store(monkeypatch):
    """Same fixture as session_manager_owner_test.py -- see its docstring."""
    from api.terminal import session_manager as terminal_session_manager

    fake_client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
    monkeypatch.setattr(terminal_session_manager, "session_configs", SessionConfigStore(redis_client=fake_client))


class TestCreateSessionTenantId:
    @pytest.mark.asyncio
    async def test_a_known_tenant_is_stamped_onto_the_session(self):
        from services.command_approval_manager import AgentRole

        mgr = SessionManager()
        session = await mgr.create_session(
            agent_id="chat_agent_1",
            agent_role=AgentRole.CHAT_AGENT,
            tenant_id="tenant-x",
        )

        assert session.tenant_id == "tenant-x"

    @pytest.mark.asyncio
    async def test_no_tenant_argument_leaves_it_unset(self):
        from services.command_approval_manager import AgentRole

        mgr = SessionManager()
        session = await mgr.create_session(agent_id="chat_agent_2", agent_role=AgentRole.CHAT_AGENT)

        assert session.tenant_id is None
