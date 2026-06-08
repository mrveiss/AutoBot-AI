# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for AgentTopology (Issue #2137).

Verifies Hebbian weight evolution, pair generation, and history recording
using in-memory stubs — no database required.
"""

import dataclasses
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock

import pytest

from .topology import AgentConnection, AgentTopology

# ---------------------------------------------------------------------------
# Helpers / Stubs
# ---------------------------------------------------------------------------


def _make_connection(
    from_agent: str = "agent_a",
    to_agent: str = "agent_b",
    task_type: str | None = "research",
    weight: float = 0.5,
    co_success_count: int = 0,
    co_failure_count: int = 0,
) -> AgentConnection:
    return AgentConnection(
        id="conn-1",
        from_agent=from_agent,
        to_agent=to_agent,
        task_type=task_type,
        weight=weight,
        co_success_count=co_success_count,
        co_failure_count=co_failure_count,
    )


def _make_db(connection: AgentConnection | None = None, delete_count: int = 0) -> AsyncMock:
    """Return a mock that satisfies the AgentTopologyDB Protocol."""
    db = AsyncMock()
    db.get_agent_connections.return_value = [connection] if connection else []
    db.get_or_create_agent_connection.return_value = connection or _make_connection()
    db.update_agent_connection.return_value = None
    db.record_agent_task.return_value = None
    db.delete_weak_connections.return_value = delete_count
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collaborators_queries_db():
    """get_collaborators forwards all parameters to db.get_agent_connections."""
    conn = _make_connection()
    db = _make_db(conn)
    topology = AgentTopology(db)

    result = await topology.get_collaborators("agent_a", task_type="research", min_weight=0.4, limit=3)

    db.get_agent_connections.assert_awaited_once_with(
        from_agent="agent_a",
        task_type="research",
        min_weight=0.4,
        limit=3,
    )
    assert result == [conn]


@pytest.mark.asyncio
async def test_record_outcome_success_reinforces():
    """Successful outcome moves the weight toward 1.0 (Hebbian reinforcement)."""
    initial_weight = 0.5
    conn = _make_connection(weight=initial_weight)
    db = _make_db(conn)
    topology = AgentTopology(db)

    await topology.record_outcome("wf-1", ["agent_a", "agent_b"], "research", True)

    expected_weight = initial_weight * 0.9 + 1.0 * 0.1  # == 0.55
    db.update_agent_connection.assert_awaited_once_with(
        conn.id,
        weight=pytest.approx(expected_weight),
        co_success_count=1,
        last_updated=ANY,
    )


@pytest.mark.asyncio
async def test_record_outcome_failure_weakens():
    """Failed outcome moves the weight toward 0.0 (Hebbian weakening)."""
    initial_weight = 0.5
    conn = _make_connection(weight=initial_weight)
    db = _make_db(conn)
    topology = AgentTopology(db)

    await topology.record_outcome("wf-2", ["agent_a", "agent_b"], "research", False)

    expected_weight = initial_weight * 0.9 + 0.0 * 0.1  # == 0.45
    db.update_agent_connection.assert_awaited_once_with(
        conn.id,
        weight=pytest.approx(expected_weight),
        co_failure_count=1,
        last_updated=ANY,
    )


@pytest.mark.asyncio
async def test_record_outcome_creates_connections_for_all_pairs():
    """Three agents produce exactly three pair updates (C(3,2) = 3)."""
    conn = _make_connection()
    db = _make_db(conn)
    topology = AgentTopology(db)

    await topology.record_outcome("wf-3", ["agent_a", "agent_b", "agent_c"], "analysis", True)

    assert db.get_or_create_agent_connection.await_count == 3
    assert db.update_agent_connection.await_count == 3

    expected_pairs = {
        ("agent_a", "agent_b"),
        ("agent_a", "agent_c"),
        ("agent_b", "agent_c"),
    }
    actual_pairs = {(c.args[0], c.args[1]) for c in db.get_or_create_agent_connection.await_args_list}
    assert actual_pairs == expected_pairs


@pytest.mark.asyncio
async def test_record_outcome_records_task_history():
    """record_agent_task is called once per participating agent."""
    conn = _make_connection()
    db = _make_db(conn)
    topology = AgentTopology(db)

    agents = ["agent_a", "agent_b", "agent_c"]
    await topology.record_outcome("wf-4", agents, "summary", True)

    assert db.record_agent_task.await_count == 3
    called_agents = {c.args[0] for c in db.record_agent_task.await_args_list}
    assert called_agents == set(agents)

    # Workflow ID and success flag must be forwarded correctly.
    for recorded_call in db.record_agent_task.await_args_list:
        assert recorded_call.args[2] == "wf-4"
        assert recorded_call.args[3] is True


@pytest.mark.asyncio
async def test_record_outcome_single_agent_no_pairs():
    """A single-agent workflow produces zero pair updates."""
    conn = _make_connection()
    db = _make_db(conn)
    topology = AgentTopology(db)

    await topology.record_outcome("wf-5", ["agent_a"], "chat", True)

    db.get_or_create_agent_connection.assert_not_awaited()
    db.update_agent_connection.assert_not_awaited()
    # But task history must still be recorded.
    db.record_agent_task.assert_awaited_once()


def test_agent_connection_dataclass_fields():
    """AgentConnection exposes exactly the required fields with correct types."""
    conn = AgentConnection(
        id="abc",
        from_agent="agent_x",
        to_agent="agent_y",
        task_type="qa",
        weight=0.75,
        co_success_count=10,
        co_failure_count=2,
    )

    assert conn.id == "abc"
    assert conn.from_agent == "agent_x"
    assert conn.to_agent == "agent_y"
    assert conn.task_type == "qa"
    assert conn.weight == 0.75
    assert conn.co_success_count == 10
    assert conn.co_failure_count == 2

    # Verify it is a proper dataclass (supports equality, fields introspection).
    field_names = {f.name for f in dataclasses.fields(conn)}
    assert field_names == {
        "id",
        "from_agent",
        "to_agent",
        "task_type",
        "weight",
        "co_success_count",
        "co_failure_count",
        "last_updated",
    }


@pytest.mark.asyncio
async def test_prune_weak_connections_calls_db():
    """prune_weak_connections forwards min_weight and a UTC cutoff to delete_weak_connections."""
    db = _make_db(delete_count=0)
    topology = AgentTopology(db)

    before_call = datetime.now(tz=timezone.utc)
    await topology.prune_weak_connections(min_weight=0.2, inactive_days=30)
    after_call = datetime.now(tz=timezone.utc)

    db.delete_weak_connections.assert_awaited_once()
    call_kwargs = db.delete_weak_connections.await_args.kwargs
    assert call_kwargs["min_weight"] == 0.2

    cutoff: datetime = call_kwargs["inactive_since"]
    # The cutoff must be 30 days before the call, within a 1-second tolerance.
    expected_low = before_call - timedelta(days=30) - timedelta(seconds=1)
    expected_high = after_call - timedelta(days=30) + timedelta(seconds=1)
    assert expected_low <= cutoff <= expected_high


@pytest.mark.asyncio
async def test_prune_returns_count():
    """prune_weak_connections returns the integer row count reported by the db."""
    db = _make_db(delete_count=7)
    topology = AgentTopology(db)

    result = await topology.prune_weak_connections()

    assert result == 7
