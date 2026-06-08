# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for TopologyAwareRouter (#2138)."""

from unittest.mock import AsyncMock, MagicMock

from agents.agent_orchestration.topology_routing import TopologyAwareRouter


def _make_topology(collaborator_ids: list[str] | None = None):
    """Build a mock topology with pre-configured collaborators."""
    topology = AsyncMock()
    connections = [_connection(cid) for cid in (collaborator_ids or [])]
    topology.get_collaborators = AsyncMock(return_value=connections)
    return topology


def _connection(agent_id: str):
    conn = MagicMock()
    conn.to_agent = agent_id
    return conn


async def test_simple_query_no_collaborators():
    """complexity='simple' produces an empty collaborators list."""
    topology = _make_topology(collaborator_ids=["agent-b"])
    router = TopologyAwareRouter(topology=topology)

    result = await router.route_with_collaborators(
        request="hello", context={"complexity": "simple"}, primary_agent_id="agent-a"
    )

    assert result["collaborators"] == []
    topology.get_collaborators.assert_not_called()


async def test_complex_query_gets_collaborators():
    """complexity='complex' triggers a topology lookup and returns collaborators."""
    topology = _make_topology(collaborator_ids=["agent-b", "agent-c"])
    router = TopologyAwareRouter(topology=topology)

    result = await router.route_with_collaborators(
        request="explain deep learning",
        context={"complexity": "complex"},
        primary_agent_id="agent-a",
    )

    assert result["collaborators"] == ["agent-b", "agent-c"]
    topology.get_collaborators.assert_awaited_once()


async def test_pattern_is_parallel_with_collaborators():
    """When collaborators are found, routing pattern is 'parallel'."""
    topology = _make_topology(collaborator_ids=["agent-b"])
    router = TopologyAwareRouter(topology=topology)

    result = await router.route_with_collaborators(
        request="multi-step task",
        context={"complexity": "multi_step"},
        primary_agent_id="agent-a",
    )

    assert result["pattern"] == "parallel"


async def test_pattern_is_single_without_collaborators():
    """When no collaborators are found, routing pattern is 'single'."""
    topology = _make_topology(collaborator_ids=[])
    router = TopologyAwareRouter(topology=topology)

    result = await router.route_with_collaborators(
        request="simple query",
        context={"complexity": "complex"},
        primary_agent_id="agent-a",
    )

    assert result["pattern"] == "single"


async def test_topology_consulted_flag():
    """topology_consulted is True only when collaborators were discovered."""
    topology_with = _make_topology(collaborator_ids=["agent-b"])
    topology_without = _make_topology(collaborator_ids=[])

    result_with = await TopologyAwareRouter(topology=topology_with).route_with_collaborators(
        request="q", context={"complexity": "multi_hop"}, primary_agent_id="a"
    )
    result_without = await TopologyAwareRouter(topology=topology_without).route_with_collaborators(
        request="q", context={"complexity": "complex"}, primary_agent_id="a"
    )

    assert result_with["topology_consulted"] is True
    assert result_without["topology_consulted"] is False
