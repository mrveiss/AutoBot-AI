# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TaskAgentScorer surfaces ranking scores instead of discarding them (#10660).

Moved from tests/enhanced_orchestration/ to tests/orchestration/ (issue #10666 B3).
"""

from __future__ import annotations

import types

import pytest

from orchestration.agent_router import TaskAgentScorer


def _scorer():
    perf = types.SimpleNamespace(
        agent_performance={
            "agent_a": types.SimpleNamespace(reliability_score=0.9, total_tasks=50),
            "agent_b": types.SimpleNamespace(reliability_score=0.5, total_tasks=10),
        }
    )
    caps = {"agent_a": {"x", "y"}, "agent_b": {"x", "y"}}
    return TaskAgentScorer(caps, perf, agent_registry=None)


@pytest.mark.asyncio
async def test_scored_returns_ranked_tuples():
    scored = await _scorer().get_agent_recommendations_scored({"x"})
    assert [a for a, _ in scored] == ["agent_a", "agent_b"]  # higher reliability ranks first
    assert all(isinstance(s, float) for _, s in scored)
    assert scored[0][1] > scored[1][1]  # descending by score


@pytest.mark.asyncio
async def test_names_only_variant_preserves_order_and_contract():
    names = await _scorer().get_agent_recommendations({"x"})
    assert names == ["agent_a", "agent_b"]  # still List[str], same ranking


@pytest.mark.asyncio
async def test_unmatched_capabilities_excluded():
    scored = await _scorer().get_agent_recommendations_scored({"z"})  # no agent has 'z'
    assert scored == []
