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
@pytest.mark.parametrize(
    "duration_ms, completed_at",
    [
        (1e20, "2026-11-09T12:00:00+00:00"),  # pre-fix: OverflowError from timedelta, escaped the guard
        (1e999, "2026-11-09T12:00:00+00:00"),  # JSON Infinity: pre-fix OverflowError, escaped
        (float("-inf"), "2026-11-09T12:00:00+00:00"),  # pre-fix OverflowError, escaped
        (float("nan"), "2026-11-09T12:00:00+00:00"),  # pre-fix ValueError, skipped (kept as a regression pin)
        ("abc", "2026-11-09T12:00:00+00:00"),  # float() ValueError
        ([1], "2026-11-09T12:00:00+00:00"),  # float() TypeError
        (60_000, "0001-01-01T00:00:00+00:00"),  # pre-fix: finished - duration underflows year 1: OverflowError
    ],
)
async def test_overflowing_or_non_finite_records_are_skipped_not_fatal(monkeypatch, duration_ms, completed_at):
    good = json.dumps(_record("ok", "completed", "2026-11-09T12:00:00+00:00"))
    bad = json.dumps(_record("bad", "completed", completed_at, duration_ms))  # allow_nan writes NaN/Infinity
    _use(monkeypatch, _redis([good, bad, good]))
    got = await feed_mod.get_agent_feed("a")
    assert got is not None
    assert [t["id"] for t in got["recentTasks"]] == ["ok", "ok"]
    assert len(got["activityTimeline"]) == 2
    json.dumps(got, allow_nan=False)  # the response stays valid JSON


_MISSING = object()


@pytest.mark.parametrize(
    "duration_ms, expected",
    [
        (_MISSING, 0),  # key absent
        (None, 0),
        (0, 0),
        ("1500", 1500),  # numeric string: float() accepts it
        (True, 1),  # bool is an int: 1 ms
        (-5, 0),  # the writer subtracts wall clocks without clamping: a real task, shown zero-length
        (-0.4, 0),
    ],
)
def test_lenient_durations_keep_the_task_with_a_non_negative_bar(duration_ms, expected):
    record = _record("t", "completed", "2026-11-09T12:00:00+00:00", duration_ms)
    if duration_ms is _MISSING:
        del record["duration_ms"]
    got = feed_mod.build_feed([record], NOW)
    assert [t["id"] for t in got["recentTasks"]] == ["t"]
    (bar,) = got["activityTimeline"]
    assert bar["duration"] == expected and bar["widthPercent"] >= 0
    json.dumps(got, allow_nan=False)


def test_non_dict_records_are_skipped_not_fatal():
    good = _record("ok", "completed", "2026-11-09T12:00:00+00:00")
    got = feed_mod.build_feed([good, [1, 2], "text", None, 7, good], NOW)
    assert [t["id"] for t in got["recentTasks"]] == ["ok", "ok"]


def test_skips_are_one_counted_warning_without_record_content(caplog):
    caplog.set_level("DEBUG", logger=feed_mod.logger.name)
    task_name = "PRIVATE-TASK-NAME"
    bad = [{"task_id": task_name, "status": "completed", "completed_at": "nope"} for _ in range(3)]
    feed_mod.build_feed(bad, NOW, agent_id="agent-x")
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "3" in warnings[0].getMessage() and "agent-x" in warnings[0].getMessage()
    assert task_name not in caplog.text


@pytest.mark.asyncio
async def test_one_bad_record_does_not_break_other_agents(monkeypatch):
    good = json.dumps(_record("ok", "completed", "2026-11-09T12:00:00+00:00"))
    bad = json.dumps(_record("bad", "completed", "2026-11-09T12:00:00+00:00", 1e20))
    _use(monkeypatch, _redis([bad], [good]))
    got = await feed_mod.get_agent_feeds(["a", "b"])
    assert got["a"]["recentTasks"] == [] and [t["id"] for t in got["b"]["recentTasks"]] == ["ok"]


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
