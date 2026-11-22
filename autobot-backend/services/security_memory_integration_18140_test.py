# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Issue #18140: host-context lookup must call a method the real memory graph has."""

from unittest.mock import AsyncMock, create_autospec

import pytest

pytest.importorskip("autobot_memory_graph")

from autobot_memory_graph import UNSCOPED_ALL_USERS, AutoBotMemoryGraph  # noqa: E402
from services.security_memory_integration import SecurityMemoryIntegration  # noqa: E402


def _spec_graph():
    """Mock restricted to the real AutoBotMemoryGraph interface (unknown attrs raise)."""
    graph = create_autospec(AutoBotMemoryGraph, instance=True)
    graph.search_entities = AsyncMock(return_value=[{"name": "Host: 10.0.0.1"}])
    graph.get_related_entities = AsyncMock(return_value=[{"entity": {"name": "svc"}}])
    return graph


def test_spec_graph_has_no_traverse_relations():
    """The call the integration used to make does not exist on the real class."""
    assert not hasattr(AutoBotMemoryGraph, "traverse_relations")
    with pytest.raises(AttributeError):
        _spec_graph().traverse_relations


@pytest.mark.asyncio
async def test_get_host_context_uses_canonical_traversal():
    graph = _spec_graph()
    integration = SecurityMemoryIntegration(memory_graph=graph)
    integration._initialized = True

    result = await integration.get_host_context("10.0.0.1", depth=2)

    graph.get_related_entities.assert_awaited_once_with(
        entity_name="Host: 10.0.0.1", max_depth=2, owner=UNSCOPED_ALL_USERS
    )
    assert result["found"] is True
    assert result["related"] == [{"entity": {"name": "svc"}}]
