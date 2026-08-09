# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory-graph resolution for the tiered context stack (#13686).

L2 OnDemand could never render: the graph was read off ``ChatWorkflowManager``,
which has no such attribute, so ``getattr(..., None)`` always won and the layer
returned "" on its first branch.

These exercise the real accessor against a seeded ``app_state`` rather than
patching the accessor itself — patching it would assert only that a mock
returns a mock, and would leave the one line carrying the fix unexecuted.
"""

from unittest.mock import MagicMock, patch

import pytest

from chat_workflow.tiered_context_sources import resolve_memory_graph
from utils.resource_factory import ResourceFactory


@pytest.fixture
def app_state():
    """Yield the real process-wide app_state dict, restored afterwards."""
    from initialization.lifespan import app_state as state

    original = state.get("chat_history_manager")
    yield state
    state["chat_history_manager"] = original


class TestInitializedManagerAccessor:
    def test_returns_the_manager_the_app_registered(self, app_state):
        """Exercises the real lookup: app_state -> manager."""
        manager = MagicMock(name="ChatHistoryManager")
        app_state["chat_history_manager"] = manager

        assert ResourceFactory.get_initialized_chat_history_manager() is manager

    def test_returns_none_before_startup_registers_one(self, app_state):
        app_state["chat_history_manager"] = None

        assert ResourceFactory.get_initialized_chat_history_manager() is None

    def test_never_constructs_a_manager(self, app_state):
        """The accessor must not pay for (or duplicate) a ChatHistoryManager."""
        app_state["chat_history_manager"] = None

        with patch("chat_history.ChatHistoryManager") as manager_cls:
            assert ResourceFactory.get_initialized_chat_history_manager() is None

        manager_cls.assert_not_called()


class TestResolveMemoryGraph:
    def test_resolves_the_graph_owned_by_the_registered_manager(self, app_state):
        """AC #13686: the graph reaching L2 is the same instance the manager owns.

        End-to-end through the real accessor — not a patched one — so the fix
        line itself is executed.
        """
        graph = MagicMock(name="AutoBotMemoryGraph")
        manager = MagicMock()
        manager.memory_graph = graph
        app_state["chat_history_manager"] = manager

        import asyncio

        assert asyncio.run(resolve_memory_graph()) is graph

    @pytest.mark.asyncio
    async def test_constructs_no_second_memory_graph(self, app_state):
        """AC #13686: no new AutoBotMemoryGraph is introduced.

        Patches the class where it is actually constructed — on ChatHistoryBase
        (``chat_history.base.AutoBotMemoryGraph``) — so the assertion can fail.
        """
        manager = MagicMock()
        manager.memory_graph = MagicMock()
        app_state["chat_history_manager"] = manager

        with patch("chat_history.base.AutoBotMemoryGraph") as graph_cls:
            await resolve_memory_graph()

        graph_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_degrades_to_none_without_a_manager(self, app_state):
        """No initialised manager (pre-startup, or outside an app) -> None."""
        app_state["chat_history_manager"] = None

        assert await resolve_memory_graph() is None

    @pytest.mark.asyncio
    async def test_degrades_to_none_when_graph_init_failed(self, app_state):
        """A manager whose graph failed to initialise leaves memory_graph None."""
        manager = MagicMock()
        manager.memory_graph = None
        app_state["chat_history_manager"] = manager

        assert await resolve_memory_graph() is None

    @pytest.mark.asyncio
    async def test_resolution_failure_is_non_fatal(self):
        """A raising accessor must not take the turn down."""
        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            side_effect=RuntimeError("boom"),
        ):
            assert await resolve_memory_graph() is None
