# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent task feeds are measured or None, never a placeholder [] (#21270)."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import agent_activity_feed as feed_mod

NOW = datetime(2026, 11, 9, 12, 30, tzinfo=timezone.utc)  # axis: 07:00 -> 13:00


def _record(task_id, status, completed_at, duration_ms=60_000):
    return {
        "task_id": task_id,
        "task_name": f"name-{task_id}",
        "status": status,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
    }


def _analytics(redis):
    analytics = MagicMock()
    analytics.AGENT_HISTORY_KEY = "agent_analytics:history"
    analytics.get_redis = AsyncMock(return_value=redis)
    return analytics


@pytest.mark.asyncio
async def test_unreadable_store_is_none_not_empty(monkeypatch):
    monkeypatch.setattr(feed_mod, "get_agent_analytics", lambda: _analytics(None))
    assert await feed_mod.get_agent_feed("a") is None


@pytest.mark.asyncio
async def test_redis_error_is_none_not_empty(monkeypatch):
    redis = MagicMock()
    redis.lrange = AsyncMock(side_effect=ConnectionError("down"))
    monkeypatch.setattr(feed_mod, "get_agent_analytics", lambda: _analytics(redis))
    assert await feed_mod.get_agent_feed("a") is None


@pytest.mark.asyncio
async def test_measured_empty_history_is_empty_lists(monkeypatch):
    redis = MagicMock()
    redis.lrange = AsyncMock(return_value=[])
    monkeypatch.setattr(feed_mod, "get_agent_analytics", lambda: _analytics(redis))
    assert await feed_mod.get_agent_feed("a") == {"recentTasks": [], "activityTimeline": []}
    redis.lrange.assert_awaited_once_with("agent_analytics:history:a", 0, feed_mod.FEED_LIMIT - 1)


@pytest.mark.asyncio
async def test_history_records_feed_both_lists(monkeypatch):
    raw = [json.dumps(_record("t1", "completed", "2026-11-09T12:00:00+00:00"))]
    redis = MagicMock()
    redis.lrange = AsyncMock(return_value=raw)
    monkeypatch.setattr(feed_mod, "get_agent_analytics", lambda: _analytics(redis))
    got = await feed_mod.get_agent_feed("a")
    assert [t["id"] for t in got["recentTasks"]] == ["t1"]
    assert len(got["activityTimeline"]) == 1


def test_build_feed_maps_status_and_skips_unfinished():
    records = [
        _record("ok", "completed", "2026-11-09T12:00:00+00:00"),
        _record("bad", "timeout", "2026-11-09T11:00:00+00:00"),
        _record("run", "running", None),
    ]
    got = feed_mod.build_feed(records, NOW)
    assert [(t["id"], t["status"]) for t in got["recentTasks"]] == [("ok", "completed"), ("bad", "failed")]
    done = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    assert got["recentTasks"][0]["completedAt"] == int(done.timestamp() * 1000)
    assert [b["type"] for b in got["activityTimeline"]] == ["working", "error"]


def test_timeline_bar_is_positioned_on_the_six_hour_axis():
    # finished 12:00, ran 60 min -> 11:00..12:00 on a 07:00..13:00 axis
    got = feed_mod.build_feed([_record("t", "completed", "2026-11-09T12:00:00+00:00", 3_600_000)], NOW)
    bar = got["activityTimeline"][0]
    assert bar["startPercent"] == pytest.approx(66.67, abs=0.01)
    assert bar["widthPercent"] == pytest.approx(16.67, abs=0.01)
    assert bar["duration"] == 3_600_000


def test_task_outside_the_axis_stays_in_recent_tasks_only():
    got = feed_mod.build_feed([_record("old", "completed", "2026-11-08T12:00:00+00:00")], NOW)
    assert len(got["recentTasks"]) == 1
    assert got["activityTimeline"] == []


def test_with_feed_none_sets_both_to_none():
    item = feed_mod.with_feed({"id": "a"}, None)
    assert item["recentTasks"] is None and item["activityTimeline"] is None
    measured = feed_mod.with_feed({"id": "a"}, {"recentTasks": [], "activityTimeline": []})
    assert measured["recentTasks"] == [] and measured["activityTimeline"] == []
