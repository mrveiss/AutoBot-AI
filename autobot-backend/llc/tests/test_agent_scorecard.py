# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for AgentScorecardService — per-agent scorecard aggregation (GH#12619)."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import LLCRunStatus, WorkItemStatus
from llc.models.sprint import LLCSprint
from llc.services.agent_scorecard import AgentScorecardService, _wilson_lower_bound
from llc.services.sprint_planning import SprintNotFound

_SPRINT_ID = uuid.uuid4()
_COMPANY_ID = uuid.uuid4()
_AGENT_A_NODE = uuid.uuid4()
_AGENT_B_NODE = uuid.uuid4()


def _patch_obj(obj, attr, new):
    return patch.object(obj, attr, new=new)


def _make_sprint(**kwargs) -> LLCSprint:
    defaults = {
        "id": _SPRINT_ID,
        "company_id": _COMPANY_ID,
        "name": "Sprint 1",
        "start_date": date(2026, 6, 1),
        "end_date": date(2026, 6, 14),
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=LLCSprint)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _agent_org_node(node_id, slug, name):
    node = MagicMock()
    node.id = node_id
    node.agent_id = slug
    node.name = name
    return node


def _agent_budget(slug, spent, tokens):
    row = MagicMock()
    row.agent_id = slug
    row.budget_spent = Decimal(str(spent))
    row.tokens_spent = tokens
    return row


def _execute_result(*, scalar_one_or_none=None, all_rows=None, scalars_all=None):
    """Build a MagicMock mimicking a SQLAlchemy Result for one canned response."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.all.return_value = all_rows or []
    if scalars_all is not None:
        result.scalars.return_value.all.return_value = scalars_all
    return result


# ---------------------------------------------------------------------------
# Pure math — Wilson lower bound + terminal-status classification
# ---------------------------------------------------------------------------


def test_wilson_lower_bound_penalizes_small_sample():
    """A 2/2 agent must not outrank a 180/200 agent on raw ratio alone."""
    small_n = _wilson_lower_bound(successes=2, total=2, z=1.96)
    large_n = _wilson_lower_bound(successes=180, total=200, z=1.96)

    assert small_n < large_n, "low-n perfect ratio should score below high-n near-perfect ratio"
    assert small_n < 1.0  # raw ratio would be 1.0; the lower bound must shrink it


def test_wilson_lower_bound_zero_total_is_zero():
    assert _wilson_lower_bound(successes=0, total=0, z=1.96) == 0.0


def test_summarize_run_counts_uses_canonical_terminal_classifier():
    svc = AgentScorecardService()
    status_counts = {
        LLCRunStatus.QUEUED.value: 3,
        LLCRunStatus.RUNNING.value: 1,
        LLCRunStatus.COMPLETED.value: 8,
        LLCRunStatus.FAILED.value: 2,
    }
    total, terminal, completed = svc._summarize_run_counts(status_counts)
    assert total == 14
    assert terminal == 10  # excludes QUEUED + RUNNING (GH#9777 is_terminal())
    assert completed == 8


# ---------------------------------------------------------------------------
# build() orchestration — mocked data-access boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_zero_run_agent_is_none_not_zero_or_error():
    """Design AC: zero-run agent gets success_rate=None, not a ZeroDivisionError or omission."""
    svc = AgentScorecardService()
    sprint = _make_sprint()
    node = _agent_org_node(_AGENT_B_NODE, "agent-b", "Agent Bravo")
    roster = {_AGENT_B_NODE: {"work_items_total": 1, "work_items_done": 0}}

    with (
        _patch_obj(svc, "_load_sprint", AsyncMock(return_value=sprint)),
        _patch_obj(svc, "_enumerate_sprint_agents", AsyncMock(return_value=roster)),
        _patch_obj(svc, "_resolve_agent_nodes", AsyncMock(return_value={_AGENT_B_NODE: node})),
        _patch_obj(svc, "_aggregate_heartbeat_runs", AsyncMock(return_value={})),
        _patch_obj(svc, "_aggregate_budgets", AsyncMock(return_value={})),
    ):
        scorecard = await svc.build(AsyncMock(), _SPRINT_ID)

    assert len(scorecard.scores) == 1
    score = scorecard.scores[0]
    assert score.runs_total == 0  # measured zero — the agent was in-window with no runs
    assert score.success_rate is None  # not 0.0 — avoids punishing idle agents
    assert score.reliability_score is None
    assert score.low_sample is None
    assert score.spend_lifetime_usd is None  # no budget row


@pytest.mark.asyncio
async def test_build_empty_roster_returns_no_scores_not_an_error():
    svc = AgentScorecardService()
    sprint = _make_sprint()
    with (
        _patch_obj(svc, "_load_sprint", AsyncMock(return_value=sprint)),
        _patch_obj(svc, "_enumerate_sprint_agents", AsyncMock(return_value={})),
    ):
        scorecard = await svc.build(AsyncMock(), _SPRINT_ID)
    assert scorecard.scores == []


@pytest.mark.asyncio
async def test_build_run_window_unavailable_without_start_date():
    """No sprint.start_date → run metrics are None (unknown), never 0 (measured)."""
    svc = AgentScorecardService()
    sprint = _make_sprint(start_date=None)
    node = _agent_org_node(_AGENT_A_NODE, "agent-a", "Agent Alpha")
    roster = {_AGENT_A_NODE: {"work_items_total": 3, "work_items_done": 2}}

    with (
        _patch_obj(svc, "_load_sprint", AsyncMock(return_value=sprint)),
        _patch_obj(svc, "_enumerate_sprint_agents", AsyncMock(return_value=roster)),
        _patch_obj(svc, "_resolve_agent_nodes", AsyncMock(return_value={_AGENT_A_NODE: node})),
        _patch_obj(svc, "_aggregate_budgets", AsyncMock(return_value={})),
    ):
        scorecard = await svc.build(AsyncMock(), _SPRINT_ID)

    assert scorecard.run_window_available is False
    score = scorecard.scores[0]
    assert score.runs_total is None
    assert score.success_rate is None
    assert score.throughput == 2  # work-item completion is independent of the run window


@pytest.mark.asyncio
async def test_build_low_sample_flag_below_configured_threshold():
    svc = AgentScorecardService()
    sprint = _make_sprint()
    node = _agent_org_node(_AGENT_A_NODE, "agent-a", "Agent Alpha")
    roster = {_AGENT_A_NODE: {"work_items_total": 1, "work_items_done": 1}}
    run_stats = {"agent-a": {LLCRunStatus.COMPLETED.value: 2}}  # 2 terminal runs < default threshold (5)

    with (
        _patch_obj(svc, "_load_sprint", AsyncMock(return_value=sprint)),
        _patch_obj(svc, "_enumerate_sprint_agents", AsyncMock(return_value=roster)),
        _patch_obj(svc, "_resolve_agent_nodes", AsyncMock(return_value={_AGENT_A_NODE: node})),
        _patch_obj(svc, "_aggregate_heartbeat_runs", AsyncMock(return_value=run_stats)),
        _patch_obj(svc, "_aggregate_budgets", AsyncMock(return_value={})),
    ):
        scorecard = await svc.build(AsyncMock(), _SPRINT_ID)

    score = scorecard.scores[0]
    assert score.success_rate == 1.0
    assert score.low_sample is True  # flagged despite a perfect ratio
    assert score.reliability_score < 1.0  # Wilson bound shrinks it below the raw ratio


@pytest.mark.asyncio
async def test_build_sprint_not_found_raises():
    svc = AgentScorecardService()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(scalar_one_or_none=None))
    with pytest.raises(SprintNotFound):
        await svc.build(session, uuid.uuid4())


# ---------------------------------------------------------------------------
# End-to-end aggregation against a sequenced mock session (real SQL-building code)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_full_aggregation_against_real_queries():
    """Exercises the real query-building methods (not mocked), matching call order in build()."""
    svc = AgentScorecardService()
    sprint = _make_sprint()

    node_a = _agent_org_node(_AGENT_A_NODE, "agent-a", "Agent Alpha")
    node_b = _agent_org_node(_AGENT_B_NODE, "agent-b", "Agent Bravo")

    roster_rows = [
        (_AGENT_A_NODE, WorkItemStatus.DONE.value),
        (_AGENT_A_NODE, WorkItemStatus.IN_PROGRESS.value),
        (_AGENT_B_NODE, WorkItemStatus.DONE.value),
    ]
    run_rows = [
        ("agent-a", LLCRunStatus.COMPLETED.value, 180),
        ("agent-a", LLCRunStatus.FAILED.value, 20),
        # agent-b has no heartbeat runs at all — zero-run case
    ]
    budget_rows = [_agent_budget("agent-a", "12.50", 500_000)]

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(scalar_one_or_none=sprint),  # _load_sprint
            _execute_result(all_rows=roster_rows),  # _enumerate_sprint_agents
            _execute_result(scalars_all=[node_a, node_b]),  # _resolve_agent_nodes
            _execute_result(all_rows=run_rows),  # _aggregate_heartbeat_runs
            _execute_result(scalars_all=budget_rows),  # _aggregate_budgets
        ]
    )

    scorecard = await svc.build(session, _SPRINT_ID)

    by_agent = {s.agent_id: s for s in scorecard.scores}
    assert set(by_agent) == {"agent-a", "agent-b"}

    a = by_agent["agent-a"]
    assert a.work_items_total == 2 and a.work_items_done == 1
    assert a.runs_terminal == 200 and a.runs_completed == 180
    assert a.success_rate == pytest.approx(0.9)
    assert a.spend_lifetime_usd == pytest.approx(12.50)
    assert a.tokens_spent_lifetime == 500_000

    b = by_agent["agent-b"]
    assert b.work_items_total == 1 and b.work_items_done == 1
    assert b.runs_total == 0
    assert b.success_rate is None
    assert b.spend_lifetime_usd is None
