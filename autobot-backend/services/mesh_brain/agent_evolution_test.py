# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for AgentEvolutionTracker (#2138)."""

from unittest.mock import AsyncMock

from services.mesh_brain.agent_evolution import (
    AgentEvolutionTracker,
    AgentSpecialization,
)


def _make_db(stats: list[dict] | None = None, agent_ids: list[str] | None = None):
    """Build a minimal mock DB matching the AgentSpecializationDB protocol."""
    db = AsyncMock()
    db.get_agent_specializations = AsyncMock(return_value=stats or [])
    db.get_all_agent_ids = AsyncMock(return_value=agent_ids or [])
    return db


def _stat(task_type: str, success_rate: float, task_count: int) -> dict:
    return {
        "task_type": task_type,
        "success_rate": success_rate,
        "task_count": task_count,
    }


async def test_evaluate_returns_specializations() -> None:
    """Stats rows are converted to AgentSpecialization objects."""
    stats = [_stat("code_gen", 0.9, 10), _stat("rag", 0.8, 7)]
    tracker = AgentEvolutionTracker(db=_make_db(stats=stats))

    result = await tracker.evaluate("agent-1")

    assert len(result) == 2
    assert all(isinstance(s, AgentSpecialization) for s in result)
    assert result[0].agent_id == "agent-1"
    assert result[0].task_type == "code_gen"
    assert result[0].success_rate == 0.9
    assert result[0].task_count == 10


async def test_evaluate_updates_registry() -> None:
    """When registry is provided, update_specializations is called."""
    stats = [_stat("code_gen", 0.9, 12)]
    registry = AsyncMock()
    registry.update_specializations = AsyncMock()

    tracker = AgentEvolutionTracker(db=_make_db(stats=stats), registry=registry)
    await tracker.evaluate("agent-2")

    registry.update_specializations.assert_called_once()
    call_args = registry.update_specializations.call_args
    assert call_args[0][0] == "agent-2"
    assert "code_gen" in call_args[0][1]


async def test_evaluate_skips_registry_when_none() -> None:
    """No error is raised when registry is None."""
    stats = [_stat("rag", 0.75, 6)]
    tracker = AgentEvolutionTracker(db=_make_db(stats=stats), registry=None)

    result = await tracker.evaluate("agent-3")

    assert len(result) == 1


async def test_evaluate_all_queries_all_agents() -> None:
    """evaluate_all calls evaluate for every agent returned by get_all_agent_ids."""
    stats = [_stat("rag", 0.85, 8)]
    db = _make_db(stats=stats, agent_ids=["a1", "a2", "a3"])

    tracker = AgentEvolutionTracker(db=db)
    result = await tracker.evaluate_all()

    assert db.get_all_agent_ids.call_count == 1
    assert db.get_agent_specializations.call_count == 3
    assert set(result.keys()) == {"a1", "a2", "a3"}


async def test_empty_stats_returns_empty_list() -> None:
    """An agent with no task history yields an empty specialization list."""
    tracker = AgentEvolutionTracker(db=_make_db(stats=[]))

    result = await tracker.evaluate("agent-empty")

    assert result == []
