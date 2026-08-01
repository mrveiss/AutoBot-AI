# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AgentScorecardService — per-agent performance scorecard for a sprint (GH#12619).

Aggregates rows the LLC already writes into a per-agent scorecard: success
rate, throughput, and spend. No new data collection.

Two schema realities shape this aggregation (see design doc
``docs/design/2026-07-26-agent-scored-retrospectives.md`` and the GH#12619
premise check for full detail):

1. ``LLCHeartbeatRun.work_item_id`` is never populated by any writer, so runs
   cannot be joined to a sprint via FK. Runs are instead attributed to a
   sprint by time-windowing ``started_at`` against the sprint's
   ``start_date``/``end_date`` — an approximation, surfaced explicitly via
   ``run_window_available``/``run_window_start``/``run_window_end`` rather
   than hidden inside a silent join.
2. Agent identity is dual-keyspace (GH#10032): ``llc_work_items.assignee_agent_id``
   is the ``AgentOrgNode`` UUID PK; ``llc_heartbeat_runs.agent_id`` and
   ``llc_agent_budgets.agent_id`` are the logical slug. Sprint-agent
   enumeration goes through work items (UUID space), then crosses over to the
   slug via ``AgentOrgNode`` before querying runs/budgets.

Spend has no per-event or time-stamped record (GH#13067 — the
``llc_cost_events`` table backing ``/costs/by-agent-model`` was never
migrated and is dead code) so it is sourced from the lifetime aggregate on
``llc_agent_budgets`` and labeled ``spend_window="lifetime"`` rather than
implied to be sprint-scoped.
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode

from ..config import SCORECARD_MIN_RUNS_FOR_CONFIDENT_RANKING, SCORECARD_WILSON_Z_SCORE
from ..models.budget import LLCAgentBudget
from ..models.enums import LLCRunStatus, WorkItemStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.sprint import LLCSprint
from ..models.work_item import LLCWorkItem
from .base import LLCServiceBase
from .sprint_planning import SprintNotFound

logger = get_logger(__name__)


@dataclass
class AgentScore:
    """Per-agent scorecard row for one sprint."""

    org_node_id: str
    agent_id: Optional[str]
    agent_name: str

    work_items_total: int
    work_items_done: int
    throughput: int

    runs_total: Optional[int]
    runs_terminal: Optional[int]
    runs_completed: Optional[int]
    success_rate: Optional[float]
    reliability_score: Optional[float]
    low_sample: Optional[bool]

    spend_lifetime_usd: Optional[float]
    tokens_spent_lifetime: Optional[int]
    spend_window: str = "lifetime"

    def to_dict(self) -> dict:
        return {
            "org_node_id": self.org_node_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "work_items_total": self.work_items_total,
            "work_items_done": self.work_items_done,
            "throughput": self.throughput,
            "runs_total": self.runs_total,
            "runs_terminal": self.runs_terminal,
            "runs_completed": self.runs_completed,
            "success_rate": self.success_rate,
            "reliability_score": self.reliability_score,
            "low_sample": self.low_sample,
            "spend_lifetime_usd": self.spend_lifetime_usd,
            "tokens_spent_lifetime": self.tokens_spent_lifetime,
            "spend_window": self.spend_window,
        }


@dataclass
class SprintScorecard:
    """Scorecard for every agent who worked a given sprint."""

    sprint_id: str
    sprint_name: str
    run_window_available: bool
    run_window_start: Optional[str]
    run_window_end: Optional[str]
    scores: List[AgentScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sprint_id": self.sprint_id,
            "sprint_name": self.sprint_name,
            "run_window_available": self.run_window_available,
            "run_window_start": self.run_window_start,
            "run_window_end": self.run_window_end,
            "scores": [s.to_dict() for s in self.scores],
        }


def _wilson_lower_bound(successes: int, total: int, z: float) -> float:
    """Wilson score interval lower bound — a low-n-aware success rate.

    Shrinks toward 0 as ``total`` shrinks, so a 1/1 agent does not outrank a
    180/200 agent the way a raw ratio would. Standard formula (used e.g. by
    Reddit/HN ranking); no external dependency required.
    """
    if total == 0:
        return 0.0
    phat = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = phat + z2 / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * total)) / total)
    return max(0.0, (center - margin) / denom)


class AgentScorecardService(LLCServiceBase):
    """Read-only aggregation of per-agent success rate, throughput, and spend."""

    async def build(self, session: AsyncSession, sprint_id: uuid.UUID) -> SprintScorecard:
        """Build the scorecard for every agent assigned work in ``sprint_id``."""
        sprint = await self._load_sprint(session, sprint_id)
        roster = await self._enumerate_sprint_agents(session, sprint_id)

        window_start, window_end = self._resolve_run_window(sprint)
        window_available = window_start is not None

        if not roster:
            return SprintScorecard(
                sprint_id=str(sprint_id),
                sprint_name=sprint.name,
                run_window_available=window_available,
                run_window_start=window_start.isoformat() if window_start else None,
                run_window_end=window_end.isoformat() if window_end else None,
                scores=[],
            )

        nodes = await self._resolve_agent_nodes(session, list(roster.keys()))
        slugs = [node.agent_id for node in nodes.values()]

        run_stats = (
            await self._aggregate_heartbeat_runs(session, sprint.company_id, slugs, window_start, window_end)
            if window_available
            else {}
        )
        budget_stats = await self._aggregate_budgets(session, slugs)

        scores = [
            self._assemble_score(org_node_id, counts, nodes.get(org_node_id), run_stats, budget_stats, window_available)
            for org_node_id, counts in roster.items()
        ]
        scores.sort(key=lambda s: s.agent_name)

        return SprintScorecard(
            sprint_id=str(sprint_id),
            sprint_name=sprint.name,
            run_window_available=window_available,
            run_window_start=window_start.isoformat() if window_start else None,
            run_window_end=window_end.isoformat() if window_end else None,
            scores=scores,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_sprint(self, session: AsyncSession, sprint_id: uuid.UUID) -> LLCSprint:
        result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))
        sprint = result.scalar_one_or_none()
        if sprint is None:
            raise SprintNotFound(f"Sprint {sprint_id} not found")
        return sprint

    async def _enumerate_sprint_agents(
        self, session: AsyncSession, sprint_id: uuid.UUID
    ) -> Dict[uuid.UUID, Dict[str, int]]:
        """Return {assignee_agent_id: {work_items_total, work_items_done}}.

        Mirrors ``SprintPlanningService.get_capacity`` — an agent is "in" a
        sprint iff they are the primary assignee of at least one work item
        with that ``sprint_id``.
        """
        stmt = select(LLCWorkItem.assignee_agent_id, LLCWorkItem.status).where(
            LLCWorkItem.sprint_id == sprint_id,
            LLCWorkItem.assignee_agent_id.is_not(None),
        )
        result = await session.execute(stmt)

        roster: Dict[uuid.UUID, Dict[str, int]] = {}
        for agent_id, status in result.all():
            counts = roster.setdefault(agent_id, {"work_items_total": 0, "work_items_done": 0})
            counts["work_items_total"] += 1
            if status == WorkItemStatus.DONE.value:
                counts["work_items_done"] += 1
        return roster

    async def _resolve_agent_nodes(
        self, session: AsyncSession, org_node_ids: List[uuid.UUID]
    ) -> Dict[uuid.UUID, AgentOrgNode]:
        """Cross the UUID keyspace (work items) to the slug keyspace (runs/budgets), GH#10032."""
        result = await session.execute(select(AgentOrgNode).where(AgentOrgNode.id.in_(org_node_ids)))
        return {node.id: node for node in result.scalars().all()}

    def _resolve_run_window(self, sprint: LLCSprint) -> tuple[Optional[datetime], Optional[datetime]]:
        """Return (start, end) UTC datetimes for time-windowing runs, or (None, None).

        Runs have no sprint FK (see module docstring) so this window is an
        approximation, not a join guarantee. Unavailable when the sprint has
        no ``start_date``.
        """
        if sprint.start_date is None:
            return None, None
        start = datetime.combine(sprint.start_date, time.min, tzinfo=timezone.utc)
        end_date: date = sprint.end_date or datetime.now(timezone.utc).date()
        end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        return start, end

    async def _aggregate_heartbeat_runs(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        slugs: List[str],
        window_start: datetime,
        window_end: datetime,
    ) -> Dict[str, Dict[str, int]]:
        """Return {agent_slug: {status: count}} for runs in the sprint's time window."""
        if not slugs:
            return {}
        stmt = (
            select(
                LLCHeartbeatRun.agent_id,
                LLCHeartbeatRun.status,
                func.count().label("n"),
            )
            .where(
                LLCHeartbeatRun.company_id == company_id,
                LLCHeartbeatRun.agent_id.in_(slugs),
                LLCHeartbeatRun.started_at >= window_start,
                LLCHeartbeatRun.started_at <= window_end,
            )
            .group_by(LLCHeartbeatRun.agent_id, LLCHeartbeatRun.status)
        )
        result = await session.execute(stmt)

        by_slug: Dict[str, Dict[str, int]] = {}
        for slug, status, n in result.all():
            by_slug.setdefault(slug, {})[status] = n
        return by_slug

    async def _aggregate_budgets(self, session: AsyncSession, slugs: List[str]) -> Dict[str, LLCAgentBudget]:
        """Return {agent_slug: LLCAgentBudget} — lifetime spend, not sprint-windowed."""
        if not slugs:
            return {}
        result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id.in_(slugs)))
        return {row.agent_id: row for row in result.scalars().all()}

    def _assemble_score(
        self,
        org_node_id: uuid.UUID,
        counts: Dict[str, int],
        node: Optional[AgentOrgNode],
        run_stats: Dict[str, Dict[str, int]],
        budget_stats: Dict[str, LLCAgentBudget],
        window_available: bool,
    ) -> AgentScore:
        slug = node.agent_id if node else None
        name = node.name if node else f"unresolved-{org_node_id}"

        # None (not 0) when the run window itself is unavailable (no sprint
        # dates) — distinct from a measured zero-run agent within a real window.
        runs_total = runs_terminal = runs_completed = None
        success_rate = reliability_score = low_sample = None
        if slug is not None and window_available:
            status_counts = run_stats.get(slug, {})
            runs_total, runs_terminal, runs_completed = self._summarize_run_counts(status_counts)
            if runs_terminal > 0:
                success_rate = runs_completed / runs_terminal
                reliability_score = _wilson_lower_bound(runs_completed, runs_terminal, SCORECARD_WILSON_Z_SCORE)
                low_sample = runs_terminal < SCORECARD_MIN_RUNS_FOR_CONFIDENT_RANKING

        budget = budget_stats.get(slug) if slug else None
        return AgentScore(
            org_node_id=str(org_node_id),
            agent_id=slug,
            agent_name=name,
            work_items_total=counts["work_items_total"],
            work_items_done=counts["work_items_done"],
            throughput=counts["work_items_done"],
            runs_total=runs_total,
            runs_terminal=runs_terminal,
            runs_completed=runs_completed,
            success_rate=success_rate,
            reliability_score=reliability_score,
            low_sample=low_sample,
            spend_lifetime_usd=float(budget.budget_spent) if budget else None,
            tokens_spent_lifetime=budget.tokens_spent if budget else None,
        )

    def _summarize_run_counts(self, status_counts: Dict[str, int]) -> tuple[int, int, int]:
        """Collapse {status: count} into (total, terminal, completed) using the canonical classifier."""
        total = sum(status_counts.values())
        terminal = 0
        completed = 0
        for status, n in status_counts.items():
            if LLCRunStatus(status).is_terminal():
                terminal += n
                if status == LLCRunStatus.COMPLETED.value:
                    completed += n
        return total, terminal, completed


__all__ = ["AgentScore", "AgentScorecardService", "SprintScorecard"]
