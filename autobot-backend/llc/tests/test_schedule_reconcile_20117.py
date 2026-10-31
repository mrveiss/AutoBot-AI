# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A member lost from ``llc:heartbeat:schedule`` comes back, and a present one is left alone (#20117)."""

import logging
import sys
from types import SimpleNamespace
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import RoutineStatus
from llc.scheduler import schedule_reconcile as rec
from llc.scheduler.routine_scheduler import RoutineScheduler

_AGENT = "ceo-acme"
_ROUTINE_ID = "6fdfdb26-6743-408c-bb5d-cdfaa13ca002"
_ROUTINE = f"routine:{_ROUTINE_ID}"


class _FakePipe:
    def __init__(self, redis) -> None:
        self.redis, self.keys = redis, []

    def exists(self, key):
        self.keys.append(key)

    async def execute(self):
        return [1 if k in self.redis.flags else 0 for k in self.keys]


class _FakeRedis:
    """ZADD with NX semantics (returns the number added), ZRANGE, and a pipeline of EXISTS."""

    def __init__(self, flags=()) -> None:
        self.scores: Dict[str, float] = {}
        self.flags = set(flags)
        self.zadds = []

    async def zadd(self, key, mapping, nx=False):
        self.zadds.append(dict(mapping))
        added = 0
        for member, score in mapping.items():
            if nx and member in self.scores:
                continue
            added += member not in self.scores
            self.scores[member] = score
        return added

    async def zrange(self, key, lo, hi):
        return [m.encode() for m in self.scores]

    def pipeline(self, transaction=True):
        return _FakePipe(self)


def _w(member, kind, cron, *keys):
    return rec._Wanted(member, kind, cron, tuple(keys))


def _wanted(agents=(), routines=()):
    return (
        patch.object(rec, "_enabled_agents", AsyncMock(return_value=[_w(a, "agent", "*/5 * * * *") for a in agents])),
        patch.object(
            rec, "_active_routines", AsyncMock(return_value=[_w(m, "routine", "0 * * * *") for m in routines])
        ),
    )


async def _run(redis, agents=(), routines=()):
    p_agents, p_routines = _wanted(agents, routines)
    with p_agents, p_routines:
        return await rec.reconcile_schedule(redis)


@pytest.mark.asyncio
async def test_lost_agent_and_routine_come_back_and_are_logged(caplog):
    redis = _FakeRedis()
    with caplog.at_level(logging.WARNING, logger=rec.logger.name):
        restored = await _run(redis, agents=[_AGENT], routines=[_ROUTINE])
    assert sorted(restored) == sorted([_AGENT, _ROUTINE])
    assert set(redis.scores) == {_AGENT, _ROUTINE}
    text = caplog.text
    assert f"restored agent {_AGENT}" in text and f"restored routine {_ROUTINE}" in text


@pytest.mark.asyncio
async def test_present_member_keeps_its_fire_time_and_is_not_logged(caplog):
    redis = _FakeRedis()
    redis.scores[_AGENT] = 123.0  # e.g. a rate-limit backoff
    with caplog.at_level(logging.WARNING, logger=rec.logger.name):
        restored = await _run(redis, agents=[_AGENT])
    assert restored == []
    assert redis.scores[_AGENT] == 123.0
    assert "restored" not in caplog.text


@pytest.mark.asyncio
async def test_agent_with_pause_flag_stays_off():
    redis = _FakeRedis(flags={f"llc:agent:{_AGENT}:paused"})
    with patch.object(
        rec,
        "_enabled_agents",
        AsyncMock(return_value=[_w(_AGENT, "agent", "* * * * *", *rec._pause_keys(_AGENT, "acme"))]),
    ):
        with patch.object(rec, "_active_routines", AsyncMock(return_value=[])):
            assert await rec.reconcile_schedule(redis) == []
    assert redis.scores == {}


@pytest.mark.asyncio
async def test_company_pause_flag_alone_keeps_agent_and_routine_off():
    """controls_service.pause_company sets only the company flag, never a per-agent one."""
    redis = _FakeRedis(flags={"llc:company:acme:paused"})
    keys = rec._pause_keys(_AGENT, "acme")
    assert "llc:company:acme:paused" in keys and f"llc:agent:{_AGENT}:paused" in keys
    agents = [_w(_AGENT, "agent", "* * * * *", *keys)]
    routines = [_w(_ROUTINE, "routine", "* * * * *", *rec._pause_keys(None, "acme"))]
    with patch.object(rec, "_enabled_agents", AsyncMock(return_value=agents)):
        with patch.object(rec, "_active_routines", AsyncMock(return_value=routines)):
            assert await rec.reconcile_schedule(redis) == []
    assert redis.scores == {}


@pytest.mark.asyncio
async def test_present_member_is_never_written():
    redis = _FakeRedis()
    redis.scores[_AGENT] = 5.0
    await _run(redis, agents=[_AGENT])
    assert redis.zadds == []


def test_off_statuses_follow_controls_service_plus_paused():
    from llc.services.controls_service import NEVER_SCHEDULED_STATUSES

    assert set(rec._OFF_STATUSES) == set(NEVER_SCHEDULED_STATUSES) | {"paused"}
    assert {"inactive", "terminated", "paused"} <= set(rec._OFF_STATUSES)
    assert not {"on_leave", "offboarding"} & set(rec._OFF_STATUSES)


@pytest.mark.asyncio
async def test_agent_query_excludes_off_statuses_and_blank_cron():
    seen = {}

    class _Session:
        async def execute(self, stmt, params):
            seen["sql"], seen["params"] = str(stmt), params
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch.object(rec, "get_async_session_factory", return_value=lambda: _Session()):
        await rec._enabled_agents()
    assert "inactive" in seen["params"]["off"] and "paused" in seen["params"]["off"]
    assert "btrim" in seen["sql"] and "ORDER BY" in seen["sql"]


@pytest.mark.asyncio
async def test_bad_cron_is_logged_and_does_not_stop_the_rest(caplog):
    redis = _FakeRedis()
    rec._reported_bad_crons.clear()
    p_agents = patch.object(
        rec,
        "_enabled_agents",
        AsyncMock(return_value=[_w("bad", "agent", "not a cron"), _w(_AGENT, "agent", "*/5 * * * *")]),
    )
    with p_agents, patch.object(rec, "_active_routines", AsyncMock(return_value=[])):
        with caplog.at_level(logging.ERROR, logger=rec.logger.name):
            restored = await rec.reconcile_schedule(redis)
            redis.scores.pop(_AGENT)
            await rec.reconcile_schedule(redis)  # a second pass must not repeat the ERROR
    assert restored == [_AGENT]
    assert caplog.text.count("could not restore agent bad") == 1


def test_interval_is_the_env_backed_constant():
    assert rec.SCHEDULE_RECONCILE_INTERVAL_SECONDS >= 30.0
    from autobot_shared import env_registry, env_registry_llc  # noqa: F401

    assert "AUTOBOT_LLC_SCHEDULE_RECONCILE_INTERVAL_SECONDS" in env_registry.REGISTRY


@pytest.mark.asyncio
async def test_failed_next_fire_zadd_after_commit_does_not_fire_a_second_run(caplog):
    redis = _FakeRedis()
    redis.zadd = AsyncMock(side_effect=RuntimeError("redis down"))
    routine = SimpleNamespace(
        status=RoutineStatus.ACTIVE, company_id=None, assignee_agent_id=None, cron_schedule="*/5 * * * *"
    )
    svc = SimpleNamespace(get=AsyncMock(return_value=routine), record_run=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("user_management.database.get_async_session_factory", return_value=lambda: ctx),
        patch("llc.services.routine_service.RoutineService", return_value=svc),
        patch("llc.scheduler.routine_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        with caplog.at_level(logging.ERROR, logger="llc.scheduler.routine_scheduler"):
            await RoutineScheduler()._dispatch_routine(_ROUTINE_ID)
    assert svc.record_run.await_count == 1
    assert redis.zadd.await_count == 1  # no retry re-add that would fire the routine again
    assert "rescheduling failed" in caplog.text


@pytest.mark.asyncio
async def test_routine_claimed_without_croniter_is_logged_and_re_added(caplog):
    redis = _FakeRedis()
    with (
        patch.dict(sys.modules, {"croniter": None}),
        patch("llc.scheduler.routine_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        with caplog.at_level(logging.ERROR, logger="llc.scheduler.routine_scheduler"):
            await RoutineScheduler()._dispatch_routine(_ROUTINE_ID)
    assert _ROUTINE in redis.scores
    assert "croniter not installed" in caplog.text
