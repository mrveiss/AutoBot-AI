# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for TopologyAwareRouter wiring into AgentRouter (#6821).

Verifies:
- TopologyAwareRouter is wired in production code (import test)
- TOPOLOGY_ROUTING_ENABLED=false skips topology augmentation
- TOPOLOGY_ROUTING_ENABLED=true augments complex routing decisions
- InMemoryTopologyDB satisfies the AgentTopologyDB Protocol
"""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Hollow package stubs — ensures agents and agents.agent_orchestration can
# be imported without pulling in heavy optional deps (llama_index, etc.).
# Follows the pattern used in test_memory_hooks.py.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ORCH_DIR = _BACKEND_DIR / "agents" / "agent_orchestration"

if "agents" not in sys.modules:
    _agents_pkg = types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_BACKEND_DIR / "agents")]  # type: ignore[assignment]
    _agents_pkg.__package__ = "agents"
    sys.modules["agents"] = _agents_pkg

if "agents.agent_orchestration" not in sys.modules:
    _orch_pkg = types.ModuleType("agents.agent_orchestration")
    _orch_pkg.__path__ = [str(_ORCH_DIR)]  # type: ignore[assignment]
    _orch_pkg.__package__ = "agents.agent_orchestration"
    sys.modules["agents.agent_orchestration"] = _orch_pkg

# Stub out rl_router so routing.py doesn't need it at import time.
if "agents.agent_orchestration.rl_router" not in sys.modules:
    _rl_stub = types.ModuleType("agents.agent_orchestration.rl_router")
    _rl_stub.RLRouter = type("RLRouter", (), {})  # type: ignore[attr-defined]
    sys.modules["agents.agent_orchestration.rl_router"] = _rl_stub

from agents.agent_orchestration.routing import AgentRouter  # noqa: E402

# Now import the real modules using normal package paths.
from agents.agent_orchestration.topology import (  # noqa: E402
    AgentTopology,
    AgentTopologyDB,
    InMemoryTopologyDB,
)
from agents.agent_orchestration.topology_routing import TopologyAwareRouter  # noqa: E402
from agents.agent_orchestration.types import (  # noqa: E402
    AgentCapabilityDescriptor,
    AgentType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_capabilities():
    return {
        AgentType.CHAT: AgentCapabilityDescriptor(
            agent_type=AgentType.CHAT,
            model_size="small",
            specialization="chat",
            strengths=["conversation"],
            limitations=[],
            resource_usage="low",
        )
    }


@pytest.fixture()
def mock_llm():
    llm = AsyncMock()
    llm.chat_completion = AsyncMock(
        return_value={
            "message": {
                "content": (
                    '{"strategy": "multi_agent", "primary_agent": "chat", '
                    '"secondary_agents": [], "confidence": 0.9, "reasoning": "test"}'
                )
            }
        }
    )
    return llm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_production_import_exists():
    """TopologyAwareRouter and AgentTopology must be imported in routing.py."""
    routing_src = (_ORCH_DIR / "routing.py").read_text()
    assert "from .topology_routing import TopologyAwareRouter" in routing_src
    assert "from .topology import AgentTopology, InMemoryTopologyDB" in routing_src


def test_topology_routing_disabled_by_default(minimal_capabilities, mock_llm):
    """topology_routing_enabled must default to False."""
    import os

    os.environ.pop("TOPOLOGY_ROUTING_ENABLED", None)
    router = AgentRouter(minimal_capabilities, mock_llm)
    assert router.topology_routing_enabled is False


def test_topology_routing_enabled_via_env(minimal_capabilities, mock_llm):
    """TOPOLOGY_ROUTING_ENABLED=true must flip the flag."""
    with patch.dict("os.environ", {"TOPOLOGY_ROUTING_ENABLED": "true"}):
        router = AgentRouter(minimal_capabilities, mock_llm)
    assert router.topology_routing_enabled is True


@pytest.mark.asyncio
async def test_topology_not_consulted_when_disabled(minimal_capabilities, mock_llm):
    """When flag is off, _maybe_augment_with_topology is a no-op."""
    import os

    os.environ.pop("TOPOLOGY_ROUTING_ENABLED", None)
    router = AgentRouter(minimal_capabilities, mock_llm)

    decision = {
        "strategy": "multi_agent",
        "primary_agent": AgentType.CHAT,
        "confidence": 0.9,
    }
    result = await router._maybe_augment_with_topology("hello", {}, decision)
    assert "topology_collaborators" not in result
    # Lazy init must not have been triggered.
    assert router._topology_router is None


@pytest.mark.asyncio
async def test_topology_consulted_for_complex_task(minimal_capabilities, mock_llm):
    """When flag is on and strategy is multi_agent, topology is consulted."""
    with patch.dict("os.environ", {"TOPOLOGY_ROUTING_ENABLED": "true"}):
        router = AgentRouter(minimal_capabilities, mock_llm)

    fake_topo_result = {
        "primary": "chat",
        "collaborators": ["research"],
        "pattern": "parallel",
        "topology_consulted": True,
    }
    topo_router = AsyncMock()
    topo_router.route_with_collaborators = AsyncMock(return_value=fake_topo_result)
    router._topology_router = topo_router

    decision = {
        "strategy": "multi_agent",
        "primary_agent": AgentType.CHAT,
        "confidence": 0.9,
    }
    result = await router._maybe_augment_with_topology("research something", {}, decision)
    assert result.get("topology_collaborators") == ["research"]
    assert result.get("topology_pattern") == "parallel"


@pytest.mark.asyncio
async def test_topology_failure_is_swallowed(minimal_capabilities, mock_llm):
    """Exceptions from the topology router must not propagate."""
    with patch.dict("os.environ", {"TOPOLOGY_ROUTING_ENABLED": "true"}):
        router = AgentRouter(minimal_capabilities, mock_llm)

    topo_router = AsyncMock()
    topo_router.route_with_collaborators = AsyncMock(side_effect=RuntimeError("db down"))
    router._topology_router = topo_router

    decision = {
        "strategy": "multi_agent",
        "primary_agent": AgentType.CHAT,
        "confidence": 0.9,
    }
    # Must not raise; original decision returned intact.
    result = await router._maybe_augment_with_topology("something", {}, decision)
    assert result["strategy"] == "multi_agent"


@pytest.mark.asyncio
async def test_in_memory_topology_db_protocol():
    """InMemoryTopologyDB must satisfy the AgentTopologyDB Protocol."""
    db = InMemoryTopologyDB()
    assert isinstance(db, AgentTopologyDB)

    conn = await db.get_or_create_agent_connection("a1", "a2", "search")
    assert conn.from_agent == "a1"
    assert conn.to_agent == "a2"
    assert 0.0 <= conn.weight <= 1.0

    await db.update_agent_connection(conn.id, weight=0.8, co_success_count=1)
    results = await db.get_agent_connections("a1", "search", min_weight=0.5, limit=10)
    assert len(results) == 1
    assert results[0].weight == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_in_memory_topology_db_delete_weak():
    """delete_weak_connections removes stale, weak entries."""
    from datetime import datetime, timedelta, timezone

    db = InMemoryTopologyDB()
    conn = await db.get_or_create_agent_connection("x", "y", None)
    await db.update_agent_connection(conn.id, weight=0.05)

    # Force last_updated into the distant past.
    db._connections[conn.id].last_updated = datetime.now(tz=timezone.utc) - timedelta(days=90)

    deleted = await db.delete_weak_connections(
        min_weight=0.1,
        inactive_since=datetime.now(tz=timezone.utc) - timedelta(days=30),
    )
    assert deleted == 1
    assert len(db._connections) == 0


def test_get_topology_router_lazy_init(minimal_capabilities, mock_llm):
    """_get_topology_router must lazily create a TopologyAwareRouter instance."""
    with patch.dict("os.environ", {"TOPOLOGY_ROUTING_ENABLED": "true"}):
        router = AgentRouter(minimal_capabilities, mock_llm)

    assert router._topology_router is None
    topo_router = router._get_topology_router()
    assert isinstance(topo_router, TopologyAwareRouter)
    # Second call must return the same singleton.
    assert router._get_topology_router() is topo_router
