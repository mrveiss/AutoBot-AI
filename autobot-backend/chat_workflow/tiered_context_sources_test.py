# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the tiered-context data sources (#13686, #13687).

These cover the two structural breaks that made L2 and L4 unable to render:
the memory graph was read off an object that never had it, and goal ancestry
was never passed at the only production call site.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.tiered_context_sources import resolve_goal_ancestry, resolve_memory_graph

# ---------------------------------------------------------------------------
# #13686 — memory graph resolution
# ---------------------------------------------------------------------------


class TestResolveMemoryGraph:
    @pytest.mark.asyncio
    async def test_returns_the_managers_own_graph_instance(self):
        """The graph handed to L2 must be the *same object* the manager owns.

        This is the #13686 regression: the old call site read
        ``getattr(self, "memory_graph", None)`` off the workflow manager, which
        has no such attribute, so L2 always received None.
        """
        graph = MagicMock(name="AutoBotMemoryGraph")
        chm = MagicMock()
        chm.memory_graph = graph

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=chm,
        ):
            resolved = await resolve_memory_graph()

        assert resolved is graph

    @pytest.mark.asyncio
    async def test_constructs_no_second_memory_graph(self):
        """Resolution must never build its own AutoBotMemoryGraph."""
        chm = MagicMock()
        chm.memory_graph = MagicMock()

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=chm,
        ):
            with patch("autobot_memory_graph.AutoBotMemoryGraph") as graph_cls:
                await resolve_memory_graph()

        graph_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_degrades_to_none_without_a_manager(self):
        """No initialised manager (pre-startup, or outside an app) -> None."""
        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=None,
        ):
            assert await resolve_memory_graph() is None

    @pytest.mark.asyncio
    async def test_degrades_to_none_when_graph_init_failed(self):
        """A manager whose graph failed to initialise leaves memory_graph None."""
        chm = MagicMock()
        chm.memory_graph = None

        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            return_value=chm,
        ):
            assert await resolve_memory_graph() is None

    @pytest.mark.asyncio
    async def test_resolution_failure_is_non_fatal(self):
        """A raising accessor must not take the turn down."""
        with patch(
            "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
            side_effect=RuntimeError("boom"),
        ):
            assert await resolve_memory_graph() is None


# ---------------------------------------------------------------------------
# #13687 — goal ancestry resolution
# ---------------------------------------------------------------------------


def _install_llc_stubs(work_item, ancestry, session_factory_probe):
    """Patch the lazily-imported LLC surface with controllable doubles."""
    goal_service = MagicMock()
    goal_service.get_goal_ancestry_for_work_item = AsyncMock(return_value=ancestry)
    work_item_service = MagicMock()
    work_item_service.get = AsyncMock(return_value=work_item)

    goal_mod = MagicMock()
    goal_mod.GoalService = MagicMock(return_value=goal_service)
    wi_mod = MagicMock()
    wi_mod.WorkItemService = MagicMock(return_value=work_item_service)
    db_mod = MagicMock()
    db_mod.get_async_session_factory = session_factory_probe

    return (
        patch.dict(
            sys.modules,
            {
                "llc.services.goal": goal_mod,
                "llc.services.work_item_service": wi_mod,
                "user_management.database": db_mod,
            },
        ),
        goal_service,
        work_item_service,
    )


def _session_factory_probe():
    """A session factory that records whether it was ever called."""
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=session_cm)
    return MagicMock(return_value=factory)


class TestResolveGoalAncestry:
    @pytest.mark.asyncio
    async def test_no_work_item_issues_no_query(self):
        """AC #13687: a turn with no linked goal must not touch the DB at all."""
        probe = _session_factory_probe()
        ctx, _, _ = _install_llc_stubs(MagicMock(), [], probe)

        with ctx:
            assert await resolve_goal_ancestry(None) is None
            assert await resolve_goal_ancestry("") is None

        probe.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_root_first_chain_for_linked_goal(self):
        import uuid

        goal_id = uuid.uuid4()
        work_item = MagicMock()
        work_item.goal_id = goal_id
        chain = [
            {"id": "1", "title": "Ship the platform", "level": "vision", "status": "active"},
            {"id": "2", "title": "Wake the context stack", "level": "objective", "status": "active"},
        ]
        ctx, goal_service, wi_service = _install_llc_stubs(work_item, chain, _session_factory_probe())

        with ctx:
            result = await resolve_goal_ancestry("wi-123")

        assert result == chain
        wi_service.get.assert_awaited_once()
        assert goal_service.get_goal_ancestry_for_work_item.await_args.args[1] == goal_id

    @pytest.mark.asyncio
    async def test_work_item_without_goal_returns_none(self):
        work_item = MagicMock()
        work_item.goal_id = None
        ctx, goal_service, _ = _install_llc_stubs(work_item, [], _session_factory_probe())

        with ctx:
            assert await resolve_goal_ancestry("wi-123") is None

        goal_service.get_goal_ancestry_for_work_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_work_item_returns_none(self):
        ctx, goal_service, _ = _install_llc_stubs(None, [], _session_factory_probe())

        with ctx:
            assert await resolve_goal_ancestry("wi-404") is None

        goal_service.get_goal_ancestry_for_work_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_chain_returns_none_so_l4_stays_silent(self):
        import uuid

        work_item = MagicMock()
        work_item.goal_id = uuid.uuid4()
        ctx, _, _ = _install_llc_stubs(work_item, [], _session_factory_probe())

        with ctx:
            assert await resolve_goal_ancestry("wi-123") is None

    @pytest.mark.asyncio
    async def test_lookup_failure_is_non_fatal(self):
        """AC #13687: a goal-lookup failure completes the turn without L4."""
        probe = MagicMock(side_effect=RuntimeError("db down"))
        ctx, _, _ = _install_llc_stubs(MagicMock(), [], probe)

        with ctx:
            assert await resolve_goal_ancestry("wi-123") is None
