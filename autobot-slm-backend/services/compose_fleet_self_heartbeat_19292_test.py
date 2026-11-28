# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One heartbeat source per node: the self-heartbeat yields to a real agent (#19292).

Live, the manager node had two writers -- this loop (``agent_version
"slm-local"``) and a real slm-agent -- alternating samples, each recomputing
the status. Loaded from disk with its service imports stubbed, since the
package conftest stubs ``services.*`` names.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from testkit.fake_async_session import FakeAsyncSession

_SLM_ROOT = Path(__file__).resolve().parent.parent
_MANAGER = "00-SLM-Manager"
_INTERVAL_S = 30


def _load():
    settings = SimpleNamespace(slm_node_id=_MANAGER, heartbeat_interval=_INTERVAL_S)
    stubs = {
        "config": SimpleNamespace(settings=settings),
        "services.database": SimpleNamespace(db_service=MagicMock()),
        "services.reconciler": SimpleNamespace(reconciler_service=MagicMock()),
    }
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            "compose_fleet_under_19292_test", _SLM_ROOT / "services" / "compose_fleet.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


cf = _load()
# The node_health_status module compose_fleet itself bound (patch.dict drops it from sys.modules).
nhs = SimpleNamespace(**cf.mark_agent_lost.__globals__)


def _manager_row(agent_version, age_s, extra_data=None):
    beat = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return SimpleNamespace(
        node_id=_MANAGER, agent_version=agent_version, last_heartbeat=beat, extra_data=extra_data or {}
    )


def _run_once(row) -> AsyncMock:
    """One self-heartbeat pass over the manager, with ``row`` as its current DB state."""
    update = AsyncMock()
    with (
        patch.object(cf, "reconciler_service", SimpleNamespace(update_node_heartbeat=update)),
        patch.object(cf, "_SELF_MANAGED_NODE_IDS", {_MANAGER}),
    ):
        asyncio.run(cf._heartbeat_self_managed_once(FakeAsyncSession(results=[[row]]), (1.0, 2.0, 3.0)))
    return update


def test_the_window_uses_the_agents_reported_interval_with_a_margin():
    beats = cf.SELF_HEARTBEAT_STANDDOWN_BEATS
    assert beats >= 1
    assert cf._agent_heartbeat_window_s(_manager_row("1.0.0", 0, {cf.AGENT_INTERVAL_KEY: 45})) == 45 * beats
    # An agent that predates the report falls back to the fleet's interval.
    assert cf._agent_heartbeat_window_s(_manager_row("1.0.0", 0)) == _INTERVAL_S * beats


def test_a_bool_or_over_cap_reported_interval_falls_back_to_the_fleets():
    """A misreporting agent must not size an unbounded window that freezes the manager's status."""
    beats = cf.SELF_HEARTBEAT_STANDDOWN_BEATS
    cap = cf.AGENT_INTERVAL_MAX_S
    for bad in (True, 0, -5, cap + 1, 10**9, "45", 45.0):
        row = _manager_row("1.0.0", 0, {cf.AGENT_INTERVAL_KEY: bad})
        assert cf._agent_heartbeat_window_s(row) == _INTERVAL_S * beats, f"{bad!r} was accepted"
    assert cf._agent_heartbeat_window_s(_manager_row("1.0.0", 0, {cf.AGENT_INTERVAL_KEY: cap})) == cap * beats


def test_stands_down_while_a_real_agent_heartbeats_the_manager():
    update = _run_once(_manager_row("1.0.0", age_s=_INTERVAL_S / 2))
    update.assert_not_awaited()


def test_resumes_once_the_real_agent_goes_silent_and_records_the_loss():
    row = _manager_row("1.0.0", age_s=_INTERVAL_S * cf.SELF_HEARTBEAT_STANDDOWN_BEATS + 1)
    update = _run_once(row)
    update.assert_awaited_once()
    assert update.await_args.kwargs["agent_version"] == nhs.SELF_AGENT_VERSION
    assert nhs.read_health_state(row).get("agent_last_beat"), "the agent's death must be recorded"


def test_keeps_heartbeating_when_no_agent_exists_and_records_no_loss():
    """Its own previous beat is not a real agent: the no-external-agent case it exists for."""
    row = _manager_row(nhs.SELF_AGENT_VERSION, age_s=1)
    update = _run_once(row)
    update.assert_awaited_once()
    assert "agent_last_beat" not in nhs.read_health_state(row)


def test_a_naive_timestamp_is_read_as_utc():
    row = _manager_row("1.0.0", age_s=1)
    row.last_heartbeat = row.last_heartbeat.replace(tzinfo=None)
    assert cf.real_agent_heartbeating(row, datetime.now(timezone.utc)) is True


def test_the_cpu_sampler_owns_its_baseline():
    """cpu_times deltas, primed at construction; never psutil.cpu_percent's shared baseline."""
    times = iter(
        [
            SimpleNamespace(user=10.0, system=0.0, idle=90.0, iowait=0.0),
            SimpleNamespace(user=40.0, system=0.0, idle=110.0, iowait=0.0),
        ]
    )
    fake = MagicMock()
    fake.cpu_times.side_effect = lambda: _Times(next(times))
    sampler = cf.CpuSampler(fake)
    assert sampler.sample() == 60.0  # 30 busy of 50 elapsed
    fake.cpu_percent.assert_not_called()


def test_the_cpu_sampler_counts_guest_time_once():
    """guest/guest_nice sit inside user/nice already; summing them again under-reports busy time."""
    times = iter(
        [
            SimpleNamespace(user=10.0, system=0.0, idle=90.0, iowait=0.0, guest=0.0, guest_nice=0.0),
            SimpleNamespace(user=40.0, system=0.0, idle=110.0, iowait=0.0, guest=30.0, guest_nice=0.0),
        ]
    )
    fake = MagicMock()
    fake.cpu_times.side_effect = lambda: _Times(next(times))
    assert cf.CpuSampler(fake).sample() == 60.0  # 30 busy of 50, not 30 of 80


class _Times(tuple):
    """A cpu_times-shaped tuple: summable, with named fields (guest fields only when given)."""

    def __new__(cls, ns):
        guest = tuple(getattr(ns, f) for f in ("guest", "guest_nice") if hasattr(ns, f))
        obj = super().__new__(cls, (ns.user, ns.system, ns.idle, ns.iowait) + guest)
        obj.idle, obj.iowait = ns.idle, ns.iowait
        for field in ("guest", "guest_nice"):
            if hasattr(ns, field):
                setattr(obj, field, getattr(ns, field))
        return obj
