# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""SprintPlanningService — capacity, velocity history, and burndown (GH#8220).

Three read-only analytics methods:

  get_capacity(session, sprint_id)
      Sum of story_points for work items assigned to agents in the sprint.
      Returns total assigned points and a per-agent breakdown.

  get_velocity_history(session, project_id, n_sprints)
      Last N *closed* sprints ordered by end_date desc.  For each sprint,
      velocity = sum(story_points) of DONE work items — computed in one
      GROUP BY query (no N+1).

  get_burndown(session, sprint_id)
      Day-by-day series from sprint start_date through min(end_date, today).
      Each entry: date + remaining story points (total_points minus cumulative
      completed points up to that date).
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import SprintStatus, WorkItemStatus
from ..models.sprint import LLCSprint
from ..models.work_item import LLCWorkItem
from .base import LLCServiceBase

logger = logging.getLogger(__name__)


class SprintNotFound(ValueError):
    """Raised when a sprint_id does not exist."""


class SprintPlanningService(LLCServiceBase):
    """Read-only sprint analytics for capacity planning, velocity, and burndown."""

    # ------------------------------------------------------------------
    # Capacity
    # ------------------------------------------------------------------

    async def get_capacity(
        self,
        session: AsyncSession,
        sprint_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Return total assigned story points and per-agent breakdown."""
        sprint = await self._get_sprint(session, sprint_id)

        stmt = select(LLCWorkItem).where(LLCWorkItem.sprint_id == sprint.id)
        result = await session.execute(stmt)
        items = result.scalars().all()

        total_points = 0
        assigned_points = 0
        unassigned_points = 0
        per_agent: Dict[str, int] = {}

        for item in items:
            pts = item.story_points or 0
            total_points += pts
            if item.assignee_agent_id is not None:
                assigned_points += pts
                agent_key = str(item.assignee_agent_id)
                per_agent[agent_key] = per_agent.get(agent_key, 0) + pts
            else:
                unassigned_points += pts

        return {
            "sprint_id": str(sprint_id),
            "sprint_name": sprint.name,
            "sprint_status": sprint.status,
            "total_points": total_points,
            "assigned_points": assigned_points,
            "unassigned_points": unassigned_points,
            "committed_points": sprint.committed_points,
            "per_agent_points": per_agent,
            "item_count": len(items),
        }

    # ------------------------------------------------------------------
    # Velocity history
    # ------------------------------------------------------------------

    async def get_velocity_history(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        n_sprints: int = 5,
    ) -> Dict[str, Any]:
        """Return velocity (done story points) for the last N closed sprints.

        Uses a single GROUP BY query instead of per-sprint SELECTs to avoid N+1.
        """
        if not 1 <= n_sprints <= 52:
            raise ValueError(f"n_sprints must be between 1 and 52, got {n_sprints}")

        sprint_stmt = (
            select(LLCSprint)
            .where(
                LLCSprint.project_id == project_id,
                LLCSprint.status == SprintStatus.CLOSED,
            )
            .order_by(LLCSprint.end_date.desc())
            .limit(n_sprints)
        )
        sprint_result = await session.execute(sprint_stmt)
        sprints = sprint_result.scalars().all()

        if not sprints:
            return {
                "project_id": str(project_id),
                "n_sprints_requested": n_sprints,
                "n_sprints_returned": 0,
                "average_velocity": None,
                "sprints": [],
            }

        sprint_ids = [s.id for s in sprints]

        # Single GROUP BY query — no N+1
        velocity_stmt = (
            select(
                LLCWorkItem.sprint_id,
                func.coalesce(func.sum(LLCWorkItem.story_points), 0).label("velocity"),
            )
            .where(
                LLCWorkItem.sprint_id.in_(sprint_ids),
                LLCWorkItem.status == WorkItemStatus.DONE,
            )
            .group_by(LLCWorkItem.sprint_id)
        )
        velocity_result = await session.execute(velocity_stmt)
        velocity_by_sprint: Dict[uuid.UUID, int] = {row.sprint_id: row.velocity for row in velocity_result}

        history: List[Dict[str, Any]] = []
        for sprint in sprints:
            velocity = velocity_by_sprint.get(sprint.id, 0)
            history.append(
                {
                    "sprint_id": str(sprint.id),
                    "sprint_name": sprint.name,
                    "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
                    "velocity": velocity,
                    "committed_points": sprint.committed_points,
                }
            )

        avg_velocity = round(sum(h["velocity"] for h in history) / len(history), 1)

        return {
            "project_id": str(project_id),
            "n_sprints_requested": n_sprints,
            "n_sprints_returned": len(history),
            "average_velocity": avg_velocity,
            "sprints": history,
        }

    # ------------------------------------------------------------------
    # Burndown
    # ------------------------------------------------------------------

    async def get_burndown(
        self,
        session: AsyncSession,
        sprint_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Return a day-by-day burndown series for the sprint.

        The series starts at sprint.start_date and ends at
        min(sprint.end_date, today).  Each entry is (date, remaining_points)
        where remaining_points = total_sprint_points - cumulative_completed_points
        up to that date.

        Work items are considered completed on the UTC date of their
        completed_at timestamp.  Items without completed_at are still open.
        """
        sprint = await self._get_sprint(session, sprint_id)

        stmt = select(LLCWorkItem).where(LLCWorkItem.sprint_id == sprint.id)
        result = await session.execute(stmt)
        items = result.scalars().all()

        total_points = sum(i.story_points or 0 for i in items)

        # Map date -> points completed on that date
        completed_by_date: Dict[date, int] = {}
        for item in items:
            if item.completed_at is not None and item.story_points:
                completed_date = item.completed_at.astimezone(timezone.utc).date()
                completed_by_date[completed_date] = completed_by_date.get(completed_date, 0) + item.story_points

        if sprint.start_date is None:
            return {
                "sprint_id": str(sprint_id),
                "sprint_name": sprint.name,
                "error": "Sprint has no start_date; burndown unavailable.",
                "series": [],
            }

        # start_date/end_date are date columns (not datetime)
        start: date = sprint.start_date
        today = datetime.now(tz=timezone.utc).date()
        end: date = sprint.end_date if sprint.end_date else today
        series_end = min(end, today)

        if start > series_end:
            return {
                "sprint_id": str(sprint_id),
                "sprint_name": sprint.name,
                "total_points": total_points,
                "series": [],
            }

        series: List[Dict[str, Any]] = []
        cumulative_done = 0
        current = start
        while current <= series_end:
            cumulative_done += completed_by_date.get(current, 0)
            series.append(
                {
                    "date": current.isoformat(),
                    "remaining": max(0, total_points - cumulative_done),
                }
            )
            current += timedelta(days=1)

        return {
            "sprint_id": str(sprint_id),
            "sprint_name": sprint.name,
            "sprint_status": sprint.status,
            "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
            "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
            "total_points": total_points,
            "series": series,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_sprint(self, session: AsyncSession, sprint_id: uuid.UUID) -> LLCSprint:
        stmt = select(LLCSprint).where(LLCSprint.id == sprint_id)
        result = await session.execute(stmt)
        sprint = result.scalar_one_or_none()
        if sprint is None:
            raise SprintNotFound(f"Sprint {sprint_id} not found")
        return sprint
