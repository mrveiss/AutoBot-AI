# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-agent recent-task and timeline feeds for the Agent Activity widget (#21270).

One implementation over the analytics history store (the same records
``GET /api/analytics/agents/tasks/recent`` reads). A feed is ``None`` when the store could
not be read ("not reported", #17514) and a real list, possibly empty, when it was.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from constants.status_enums import TaskStatus
from services.agent_analytics import get_agent_analytics

logger = get_logger(__name__)

FEED_LIMIT = 20
# The widget's timeline axis: the last six clock hours, ending at the next hour boundary.
TIMELINE_HOURS = 6
_WIDGET_STATUS = {
    TaskStatus.COMPLETED.value: "completed",
    TaskStatus.FAILED.value: "failed",
    TaskStatus.TIMEOUT.value: "failed",
    TaskStatus.CANCELLED.value: "cancelled",
}
_BAR_TYPE = {"completed": "working", "failed": "error", "cancelled": "idle"}

Feed = Dict[str, List[Dict[str, Any]]]


def _window(now: datetime) -> tuple[datetime, float]:
    """(start, span in seconds) of the timeline axis for ``now``."""
    end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return end - timedelta(hours=TIMELINE_HOURS), TIMELINE_HOURS * 3600.0


def _recent_task(record: Dict[str, Any], status: str, finished: datetime) -> Dict[str, Any]:
    return {
        "id": record["task_id"],
        "name": record.get("task_name") or record["task_id"],
        "status": status,
        "completedAt": int(finished.timestamp() * 1000),
    }


def _timeline_bar(record: Dict[str, Any], status: str, finished: datetime, win: tuple) -> Dict[str, Any] | None:
    """A bar for a finished task that overlaps the axis, clipped to it; None when outside."""
    start, span = win
    duration_ms = float(record.get("duration_ms") or 0)
    began = finished - timedelta(milliseconds=duration_ms)
    left = max((began - start).total_seconds(), 0.0)
    right = min((finished - start).total_seconds(), span)
    if right <= 0 or left >= span:
        return None
    return {
        "task": record.get("task_name") or record["task_id"],
        "type": _BAR_TYPE[status],
        "startPercent": round(left / span * 100, 2),
        "widthPercent": round((right - left) / span * 100, 2),
        "duration": int(duration_ms),
    }


def build_feed(records: List[Dict[str, Any]], now: datetime | None = None) -> Feed:
    """Turn analytics task records into the widget's ``recentTasks`` / ``activityTimeline``."""
    win = _window(now or now_utc())
    tasks: List[Dict[str, Any]] = []
    bars: List[Dict[str, Any]] = []
    for record in records:
        status = _WIDGET_STATUS.get(str(record.get("status")))
        finished = parse_utc_iso(record["completed_at"]) if record.get("completed_at") else None
        if status is None or finished is None:
            continue  # still running: not a finished task
        tasks.append(_recent_task(record, status, finished))
        bar = _timeline_bar(record, status, finished, win)
        if bar is not None:
            bars.append(bar)
    return {"recentTasks": tasks, "activityTimeline": bars}


async def get_agent_feed(agent_id: str) -> Feed | None:
    """The agent's feed, or ``None`` when the history store cannot be read (not "no tasks")."""
    analytics = get_agent_analytics()
    try:
        redis = await analytics.get_redis()
        if redis is None:
            return None
        raw = await redis.lrange(f"{analytics.AGENT_HISTORY_KEY}:{agent_id}", 0, FEED_LIMIT - 1)
        return build_feed([json.loads(r) for r in raw])
    except Exception as exc:
        logger.warning("Agent activity feed for %s unreadable, reporting none: %s", agent_id, exc)
        return None


async def get_agent_feeds(agent_ids: List[str]) -> Dict[str, Feed | None]:
    """agent_id -> feed (or None), for the status endpoint and its registry fallback."""
    return {agent_id: await get_agent_feed(agent_id) for agent_id in agent_ids}


def with_feed(item: Dict[str, Any], feed: Feed | None) -> Dict[str, Any]:
    """``item`` carrying the feed's two lists, or None for both when unmeasured."""
    return {
        **item,
        "recentTasks": None if feed is None else feed["recentTasks"],
        "activityTimeline": None if feed is None else feed["activityTimeline"],
    }
