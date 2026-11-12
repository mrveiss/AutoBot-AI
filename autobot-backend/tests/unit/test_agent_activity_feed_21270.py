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
from services.agent_analytics import AgentAnalytics

NOW = datetime(2026, 11, 9, 12, 30, tzinfo=timezone.utc)  # axis: 07:00 -> 13:00


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """Every test sees the same "now": get_agent_feeds builds feeds with the module's now_utc."""
    monkeypatch.setattr(feed_mod, "now_utc", lambda: NOW)


def _record(task_id, status, completed_at, duration_ms=60_000):
    return {
        "task_id": task_id,
        "task_name": f"name-{task_id}",
        "status": status,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
    }


def _redis(*lists, error=None):
    """A Redis double whose pipeline returns one raw list per queued lrange."""
    pipe = MagicMock()
    pipe.execute = AsyncMock(side_effect=error, return_value=list(lists))
    redis = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)
    redis.pipe = pipe
    return redis


def _use(monkeypatch, redis):
    analytics = AgentAnalytics()
    analytics.get_redis = AsyncMock(return_value=redis)
    monkeypatch.setattr(feed_mod, "get_agent_analytics", lambda: analytics)
    return analytics


@pytest.mark.asyncio
async def test_unreadable_store_is_none_not_empty(monkeypatch):
    _use(monkeypatch, None)
    assert await feed_mod.get_agent_feed("a") is None


@pytest.mark.asyncio
async def test_redis_error_is_none_not_empty(monkeypatch):
    _use(monkeypatch, _redis(error=ConnectionError("down")))
    assert await feed_mod.get_agent_feed("a") is None


@pytest.mark.asyncio
async def test_measured_empty_history_is_empty_lists(monkeypatch):
    redis = _redis([])
    _use(monkeypatch, redis)
    got = await feed_mod.get_agent_feed("a")
    assert got["recentTasks"] == [] and got["activityTimeline"] == []
    redis.pipe.lrange.assert_called_once_with("agent_analytics:history:a", 0, feed_mod.FEED_LIMIT - 1)


@pytest.mark.asyncio
async def test_history_records_feed_both_lists(monkeypatch):
    raw = [json.dumps(_record("t1", "completed", "2026-11-09T12:00:00+00:00"))]
    _use(monkeypatch, _redis(raw))
    got = await feed_mod.get_agent_feed("a")
    assert [t["id"] for t in got["recentTasks"]] == ["t1"]
    assert len(got["activityTimeline"]) == 1


@pytest.mark.asyncio
async def test_many_agents_are_one_pipelined_round_trip(monkeypatch):
    redis = _redis([], [])
    _use(monkeypatch, redis)
    got = await feed_mod.get_agent_feeds(["a", "b"])
    assert set(got) == {"a", "b"} and all(v is not None for v in got.values())
    assert redis.pipe.execute.await_count == 1 and redis.pipe.lrange.call_count == 2


@pytest.mark.asyncio
async def test_agents_beyond_the_cap_report_none(monkeypatch):
    monkeypatch.setattr(feed_mod, "FEED_MAX_AGENTS", 1)
    redis = _redis([])
    _use(monkeypatch, redis)
    got = await feed_mod.get_agent_feeds(["a", "b"])
    assert got["a"] is not None and got["b"] is None
    assert redis.pipe.lrange.call_count == 1


@pytest.mark.asyncio
async def test_bad_records_are_skipped_not_fatal(monkeypatch):
    good = json.dumps(_record("ok", "completed", "2026-11-09T12:00:00+00:00"))
    no_id = json.dumps({"status": "completed", "completed_at": "2026-11-09T12:00:00+00:00"})
    bad_time = json.dumps(_record("bt", "completed", "not-a-time"))
    _use(monkeypatch, _redis([good, "{not json", no_id, bad_time, good]))
    got = await feed_mod.get_agent_feed("a")
    assert got is not None
    assert [t["id"] for t in got["recentTasks"]] == ["ok", "ok"]


@pytest.mark.asyncio
async def test_get_agent_history_keeps_empty_on_failure(monkeypatch):
    analytics = _use(monkeypatch, None)
    assert await analytics.get_agent_history("a") == []
    assert await analytics.read_agent_history("a") is None


def test_feed_carries_the_axis_start_utc_ms():
    got = feed_mod.build_feed([], NOW)
    assert got["windowStart"] == int(datetime(2026, 11, 9, 7, tzinfo=timezone.utc).timestamp() * 1000)


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
    measured = feed_mod.with_feed({"id": "a"}, {"recentTasks": [], "activityTimeline": [], "windowStart": 5})
    assert measured["recentTasks"] == [] and measured["activityTimeline"] == []
    assert measured["activityWindowStart"] == 5 and item["activityWindowStart"] is None
