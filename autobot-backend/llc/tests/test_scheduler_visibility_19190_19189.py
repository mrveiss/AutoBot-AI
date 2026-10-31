# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scheduler's decisions reach the log, and an enabled agent stays scheduled (#19190, #19189).

#19190: the scheduler modules used ``logging.getLogger(__name__)``. Only
``autobot_shared.logging_manager.get_logger`` attaches the file/stdout handlers
(the root logger has none), so INFO records were dropped and WARNING+ fell to
the stderr last-resort path, i.e. ``backend-error.log`` and not ``backend.log``.

#19189: ``LLCHeartbeatScheduler`` and ``RoutineScheduler`` share one sorted set and
each ``ZREM``-claimed every due member, including the other's, then ignored it.
"""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler import heartbeat_scheduler as hbs_module
from llc.scheduler.heartbeat_scheduler import _SCHEDULE_KEY, LLCHeartbeatScheduler
from llc.scheduler.routine_scheduler import RoutineScheduler

_HBS = "llc.scheduler.heartbeat_scheduler"
_SCHEDULER_DIR = Path(hbs_module.__file__).parent
_AGENT = "ceo-acme"
_ROUTINE = "routine:6fdfdb26-6743-408c-bb5d-cdfaa13ca002"


class _FakeSortedSet:
    """The slice of redis the pollers use, with real ZADD/ZREM/ZRANGEBYSCORE semantics."""

    def __init__(self) -> None:
        self.scores: Dict[str, float] = {}

    async def zadd(self, key, mapping, nx=False, gt=False):
        for member, score in mapping.items():
            if nx and member in self.scores:
                continue
            if gt and member in self.scores and score <= self.scores[member]:
                continue
            self.scores[member] = score

    async def zrem(self, key, member):
        return 1 if self.scores.pop(member, None) is not None else 0

    async def zrangebyscore(self, key, lo, hi, withscores=False):
        top = float("inf") if hi == "+inf" else float(hi)
        return [m.encode() for m, s in sorted(self.scores.items(), key=lambda kv: kv[1]) if s <= top]

    hincrby = hset = expire = AsyncMock()


def _agent(**over: Any) -> Dict[str, Any]:
    row = {
        "agent_id": _AGENT,
        "agent_node_id": "node-1",
        "company_id": "00000000-0000-0000-0000-000000000001",
        "name": "Acme CEO",
        "heartbeat_cron": "* * * * *",
        "heartbeat_enabled": True,
        "adapter_type": "claude_code",
        "adapter_config": {},
        "context_mode": "slim",
    }
    row.update(over)
    return row


def _session_factory() -> MagicMock:
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


async def _poll_once(fake: _FakeSortedSet, *, has_work: bool, agent=None, scheduler=None) -> LLCHeartbeatScheduler:
    scheduler = scheduler or LLCHeartbeatScheduler()
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=fake)),
        patch(f"{_HBS}.get_async_session_factory", _session_factory()),
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=agent or _agent())),
        patch.object(scheduler, "_find_rate_limited_run", AsyncMock(return_value=None)),
        patch.object(scheduler, "_create_run", AsyncMock(return_value=MagicMock(id="run-1"))),
        patch.object(scheduler, "_run_adapter", AsyncMock()),
        patch(f"{_HBS}.enrich_run_context", AsyncMock()),
        patch(f"{_HBS}.acquire_run_workspace", AsyncMock(return_value=True)),
        patch(f"{_HBS}.has_pending_work", AsyncMock(return_value=has_work)),
    ):
        await scheduler._dispatch_due()
    return scheduler


# ---------------------------------------------------------------------------
# #19190: the logging path
# ---------------------------------------------------------------------------


def _scheduler_modules() -> list[Path]:
    return [p for p in sorted(_SCHEDULER_DIR.glob("*.py")) if "test" not in p.name]


@pytest.mark.parametrize("path", _scheduler_modules(), ids=lambda p: p.name)
def test_no_scheduler_module_uses_the_bare_stdlib_logger(path: Path):
    """A bare ``logging.getLogger`` has no handler under the root, so its INFO is dropped."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "getLogger"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "logging"
    ]
    assert bare == [], f"{path.name} uses logging.getLogger at line(s) {bare}; use get_logger"


def test_the_scheduler_logger_is_the_one_the_modules_name():
    """Every scheduler module asks ``get_logger`` for its own module name (the conftest stub
    returns the stdlib logger of that name, so the name is what can be asserted here)."""
    assert hbs_module.logger.name == "llc.scheduler.heartbeat_scheduler"


def test_the_configured_logging_path_writes_a_scheduler_record_to_the_backend_log(tmp_path, monkeypatch):
    """The real ``LoggingManager`` (the conftest replaces the module-level ``get_logger`` with a stub):
    a record from the scheduler's logger name lands in ``backend.log``, which a bare
    ``logging.getLogger`` logger never did (no handler anywhere above it)."""
    from autobot_shared import logging_manager as lm

    name = "llc.scheduler.heartbeat_scheduler"
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(lm.LoggingManager, "_loggers", {})
    monkeypatch.setattr(lm.LoggingManager, "_initialized", False)
    stdlib = logging.getLogger(name)
    saved = (list(stdlib.handlers), list(stdlib.filters), stdlib.level)
    stdlib.handlers.clear()
    try:
        logger = lm.LoggingManager.get_logger(name)
        assert logger.handlers and logger.isEnabledFor(logging.INFO)
        logger.info("scheduler visibility probe")
        for handler in logger.handlers:
            handler.flush()
        assert "scheduler visibility probe" in (tmp_path / "backend.log").read_text(encoding="utf-8")
    finally:
        for handler in list(stdlib.handlers):
            handler.close()
        stdlib.handlers[:] = saved[0]
        stdlib.filters[:] = saved[1]
        stdlib.setLevel(saved[2])


def test_a_scheduler_record_reaches_caplog_under_its_real_logger_name(caplog):
    with caplog.at_level(logging.INFO, logger=_HBS):
        hbs_module.logger.info("visibility probe")
    assert [(r.name, r.getMessage()) for r in caplog.records] == [(_HBS, "visibility probe")]


@pytest.mark.asyncio
async def test_startup_logs_agent_counts(caplog):
    fake = _FakeSortedSet()
    scheduler = LLCHeartbeatScheduler()
    agents = [_agent(), _agent(agent_id="dev-1")]
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=fake)),
        patch.object(scheduler, "_load_enabled_agents", AsyncMock(return_value=agents)),
        patch.object(scheduler, "_restore_rate_limited_agents", AsyncMock()),
        caplog.at_level(logging.INFO, logger=_HBS),
    ):
        await scheduler._repopulate_schedule()
    assert "Scheduled 2 of 2 heartbeat-enabled agents" in caplog.text


@pytest.mark.asyncio
async def test_dispatch_logs_run_created_and_reschedule(caplog):
    fake = _FakeSortedSet()
    fake.scores[_AGENT] = time.time() - 1
    with caplog.at_level(logging.INFO, logger=_HBS):
        await _poll_once(fake, has_work=True)
    assert f"Heartbeat run run-1 created for agent {_AGENT}" in caplog.text
    assert f"Heartbeat scheduled agent={_AGENT} run=run-1" in caplog.text


@pytest.mark.asyncio
async def test_an_idle_wake_is_logged_with_its_reason(caplog):
    fake = _FakeSortedSet()
    fake.scores[_AGENT] = time.time() - 1
    with caplog.at_level(logging.INFO, logger=_HBS):
        await _poll_once(fake, has_work=False)
    assert f"wake skipped for agent {_AGENT}: no eligible work" in caplog.text


@pytest.mark.asyncio
async def test_a_dropped_agent_says_why(caplog):
    fake = _FakeSortedSet()
    fake.scores[_AGENT] = time.time() - 1
    scheduler = LLCHeartbeatScheduler()
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=fake)),
        patch(f"{_HBS}.get_async_session_factory", _session_factory()),
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=None)),
        caplog.at_level(logging.INFO, logger="llc.scheduler"),
    ):
        await scheduler._dispatch_due()
    assert "removed from the schedule: no heartbeat-enabled agent row" in caplog.text
    assert _AGENT not in fake.scores


@pytest.mark.asyncio
async def test_a_dispatch_error_requeues_and_logs(caplog):
    fake = _FakeSortedSet()
    fake.scores[_AGENT] = time.time() - 1
    scheduler = LLCHeartbeatScheduler()
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=fake)),
        patch.object(scheduler, "_handle_due_agent", AsyncMock(side_effect=RuntimeError("db down"))),
        caplog.at_level(logging.INFO, logger=_HBS),
    ):
        await scheduler._dispatch_due()
    assert _AGENT in fake.scores
    assert "re-queued" in caplog.text and "dispatch error" in caplog.text
    assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


# ---------------------------------------------------------------------------
# #19189: the agent stays on the schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_puts_every_enabled_agent_on_the_schedule():
    fake = _FakeSortedSet()
    fake.scores[_ROUTINE] = time.time() + 3600
    scheduler = LLCHeartbeatScheduler()
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=fake)),
        patch.object(scheduler, "_load_enabled_agents", AsyncMock(return_value=[_agent()])),
        patch.object(scheduler, "_restore_rate_limited_agents", AsyncMock()),
    ):
        await scheduler._repopulate_schedule()
    assert _AGENT in fake.scores and _ROUTINE in fake.scores


@pytest.mark.asyncio
@pytest.mark.parametrize("has_work", [True, False])
async def test_the_agent_is_back_on_the_schedule_after_every_wake_outcome(has_work):
    fake = _FakeSortedSet()
    fake.scores[_AGENT] = time.time() - 1
    await _poll_once(fake, has_work=has_work)
    assert fake.scores[_AGENT] > time.time(), "agent missing or still due after the dispatch"


@pytest.mark.asyncio
async def test_the_heartbeat_poller_leaves_a_due_routine_for_the_routine_poller():
    fake = _FakeSortedSet()
    fake.scores[_ROUTINE] = time.time() - 1
    fake.scores[_AGENT] = time.time() - 1
    await _poll_once(fake, has_work=False)
    assert _ROUTINE in fake.scores, "the heartbeat poller claimed a routine member and dropped it"
    assert _AGENT in fake.scores


@pytest.mark.asyncio
async def test_the_routine_poller_leaves_a_due_agent_for_the_heartbeat_poller():
    """The #19189 defect: this poller ZREMed the agent id and then ignored it."""
    fake = _FakeSortedSet()
    due = time.time() - 1
    fake.scores[_ROUTINE] = due
    fake.scores[_AGENT] = due
    poller = RoutineScheduler()
    dispatch = AsyncMock()
    with (
        patch("llc.scheduler.routine_scheduler.get_async_redis_client", AsyncMock(return_value=fake)),
        patch.object(poller, "_dispatch_routine", dispatch),
    ):
        await poller._process_due()
    dispatch.assert_awaited_once_with(_ROUTINE[len("routine:") :])
    assert fake.scores.get(_AGENT) == due, "the routine poller consumed an agent's schedule entry"


def test_the_set_shares_one_key_between_both_pollers():
    from llc.scheduler.routine_scheduler import _SCHEDULE_KEY as routine_key

    assert routine_key == _SCHEDULE_KEY
