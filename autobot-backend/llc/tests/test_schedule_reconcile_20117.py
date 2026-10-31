# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A member lost from ``llc:heartbeat:schedule`` comes back, and a present one is left alone (#20117)."""

import logging
import sys
from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest

from llc.scheduler import schedule_reconcile as rec
from llc.scheduler.routine_scheduler import RoutineScheduler

_AGENT = "ceo-acme"
_ROUTINE_ID = "6fdfdb26-6743-408c-bb5d-cdfaa13ca002"
_ROUTINE = f"routine:{_ROUTINE_ID}"


class _FakeRedis:
    """ZADD with NX semantics (returns the number added) and EXISTS for pause flags."""

    def __init__(self, flags=()) -> None:
        self.scores: Dict[str, float] = {}
        self.flags = set(flags)

    async def zadd(self, key, mapping, nx=False):
        added = 0
        for member, score in mapping.items():
            if nx and member in self.scores:
                continue
            added += member not in self.scores
            self.scores[member] = score
        return added

    async def exists(self, key):
        return 1 if key in self.flags else 0


def _wanted(agents=(), routines=()):
    return (
        patch.object(rec, "_enabled_agents", AsyncMock(return_value=[(a, "agent", "*/5 * * * *") for a in agents])),
        patch.object(rec, "_active_routines", AsyncMock(return_value=[(m, "routine", "0 * * * *") for m in routines])),
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
    assert await _run(redis, agents=[_AGENT]) == []
    assert redis.scores == {}


@pytest.mark.asyncio
async def test_bad_cron_is_logged_and_does_not_stop_the_rest(caplog):
    redis = _FakeRedis()
    p_agents = patch.object(
        rec,
        "_enabled_agents",
        AsyncMock(return_value=[("bad", "agent", "not a cron"), (_AGENT, "agent", "*/5 * * * *")]),
    )
    with p_agents, patch.object(rec, "_active_routines", AsyncMock(return_value=[])):
        with caplog.at_level(logging.ERROR, logger=rec.logger.name):
            restored = await rec.reconcile_schedule(redis)
    assert restored == [_AGENT]
    assert "could not restore agent bad" in caplog.text


def test_interval_is_the_env_backed_constant():
    assert rec.SCHEDULE_RECONCILE_INTERVAL_SECONDS >= 5.0
    from autobot_shared import env_registry, env_registry_llc  # noqa: F401

    assert "AUTOBOT_LLC_SCHEDULE_RECONCILE_INTERVAL_SECONDS" in env_registry.REGISTRY


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
