# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-agent recent-task and timeline feeds for the Agent Activity widget (#21270).

One implementation over the analytics history store (the same records
``GET /api/analytics/agents/tasks/recent`` reads). A feed is ``None`` when the store could
not be read ("not reported", #17514) and a real list, possibly empty, when it was.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from constants.status_enums import TaskStatus
from services.agent_analytics import get_agent_analytics

logger = get_logger(__name__)

# Env-backed caps: records read per agent, and agents read per status call.
FEED_LIMIT = env_int_clamped("AUTOBOT_AGENT_FEED_RECORDS", 20, min_v=1, max_v=200)
FEED_MAX_AGENTS = env_int_clamped("AUTOBOT_AGENT_FEED_MAX_AGENTS", 200, min_v=1, max_v=5000)
# The widget's timeline axis: the last six clock hours, ending at the next hour boundary.
TIMELINE_HOURS = 6
_WIDGET_STATUS = {
    TaskStatus.COMPLETED.value: "completed",
    TaskStatus.FAILED.value: "failed",
    TaskStatus.TIMEOUT.value: "failed",
    TaskStatus.CANCELLED.value: "cancelled",
}
_BAR_TYPE = {"completed": "working", "failed": "error", "cancelled": "idle"}

Feed = Dict[str, Any]  # recentTasks, activityTimeline: lists; windowStart: UTC ms of the axis start


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


def _record_entries(record: Dict[str, Any], win: tuple) -> tuple | None:
    """(task, bar-or-None) for a finished record; None for a running one. Raises on a bad record."""
    status = _WIDGET_STATUS.get(str(record.get("status")))
    finished = parse_utc_iso(record["completed_at"]) if record.get("completed_at") else None
    if status is None or finished is None:
        return None  # still running: not a finished task
    return _recent_task(record, status, finished), _timeline_bar(record, status, finished, win)


def build_feed(records: List[Dict[str, Any]], now: datetime | None = None) -> Feed:
    """Turn analytics task records into the widget's feed; a bad record is logged and skipped."""
    win = _window(now or now_utc())
    tasks: List[Dict[str, Any]] = []
    bars: List[Dict[str, Any]] = []
    for record in records:
        try:
            entry = _record_entries(record, win)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Skipping malformed task record in agent feed: %r", exc)
            continue
        if entry is not None:
            tasks.append(entry[0])
            bars.extend([entry[1]] if entry[1] is not None else [])
    return {
        "recentTasks": tasks,
        "activityTimeline": bars,
        "windowStart": int(win[0].timestamp() * 1000),
    }


async def get_agent_feeds(agent_ids: List[str]) -> Dict[str, Feed | None]:
    """agent_id -> feed (or None when the store is unreadable), in one pipelined read.

    Only the first ``FEED_MAX_AGENTS`` agents are read; the rest report None (not measured).
    """
    read = list(agent_ids)[:FEED_MAX_AGENTS]
    try:
        histories = await get_agent_analytics().read_agent_histories(read, FEED_LIMIT)
    except Exception as exc:
        logger.warning("Agent activity feeds unreadable, reporting none: %s", exc)
        histories = None
    feeds = {a: None for a in agent_ids}
    if histories is not None:
        feeds.update({a: build_feed(records) for a, records in histories.items()})
    return feeds


async def get_agent_feed(agent_id: str) -> Feed | None:
    """One agent's feed, or ``None`` when the history store cannot be read (not "no tasks")."""
    return (await get_agent_feeds([agent_id]))[agent_id]


def with_feed(item: Dict[str, Any], feed: Feed | None) -> Dict[str, Any]:
    """``item`` carrying the feed's two lists, or None for both when unmeasured."""
    return {
        **item,
        "recentTasks": None if feed is None else feed["recentTasks"],
        "activityTimeline": None if feed is None else feed["activityTimeline"],
        "activityWindowStart": None if feed is None else feed["windowStart"],
    }
