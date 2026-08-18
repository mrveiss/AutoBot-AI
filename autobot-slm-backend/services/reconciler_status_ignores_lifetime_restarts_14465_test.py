# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node stays degraded forever while heartbeating healthily (#14465, defect 1).

Root cause, verified independently of the issue's own write-up: `_calculate_node_status`
degraded on two signals for a crash-looping ``autobot*`` service --
``status == "crash-loop"`` (systemd's own `activating`+`auto-restart` sub-state,
true only while a unit is presently churning) and ``n_restarts > 3`` (systemd's
`NRestarts` property, read in `health_collector._get_service_details`).

`NRestarts` is a lifetime-cumulative counter -- systemd never resets it except at
reboot or `systemctl reset-failed`. Used as a static absolute-threshold gate, it
can only ever climb: once any ``autobot*`` service anywhere in a node's uptime
crosses 3 restarts (a redeploy, an operator restart, a genuine but long-resolved
crash-loop), every future heartbeat computes DEGRADED regardless of current
metrics or the service's current state, with no path back to ONLINE. That is
exactly this issue's evidence: cpu 0.0 / memory 23.4 / disk 18.1, no metric near
either threshold, yet the node stays degraded across at least 50 minutes of
healthy heartbeats.

The node's roles are ``[vnc, slm-agent]``; ``ansible/roles/browser/tasks/main.yml``
deploys a real ``autobot-vnc.service`` unit on such nodes, so the crash-loop branch
in `_calculate_node_status` is reachable for this node shape without requiring any
DB read this repo cannot make -- the bug is provable from the function alone.

The module is loaded from disk, not imported, because the package conftest stubs
`services.*` and a plain `import services.reconciler` yields a MagicMock that
would satisfy every check here while exercising nothing (see
`reconciler_heartbeat_verification_test.py` for the same rationale).
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconciler_under_status_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_status_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()

# Healthy metrics straight from the issue's evidence.
_CPU, _MEM, _DISK = 0.0, 23.4, 18.1


def _status(extra_data=None) -> str:
    """Call the real `_calculate_node_status` -- it does not touch `self`."""
    return reconciler.ReconcilerService._calculate_node_status(SimpleNamespace(), _CPU, _MEM, _DISK, extra_data)


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.isfunction(reconciler.ReconcilerService._calculate_node_status)


def test_a_service_that_restarted_long_ago_but_is_now_running_is_not_degraded():
    """The defect, reproduced directly.

    `autobot-vnc` crossed 3 restarts at some point in the node's uptime (a
    redeploy, a past crash that has since resolved -- the cause is irrelevant,
    `NRestarts` does not record *when*) and is presently `status: "running"`.
    Healthy metrics, no active crash-loop: this must be ONLINE.
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-vnc", "status": "running", "n_restarts": 5},
            {"name": "slm-agent", "status": "running", "n_restarts": 12},
        ]
    }

    assert _status(extra_data) == reconciler.NodeStatus.ONLINE.value, (
        "a service with a high LIFETIME restart count but a currently healthy "
        "state pinned the node DEGRADED forever (#14465)"
    )


def test_a_presently_crash_looping_service_still_degrades_the_node():
    """Issue #1604's actual intent must survive this fix.

    `status == "crash-loop"` reflects systemd's `activating`+`auto-restart`
    sub-state -- true only while the unit is presently churning -- and is kept
    unchanged by this fix.
    """
    extra_data = {"discovered_services": [{"name": "autobot-vnc", "status": "crash-loop", "n_restarts": 1}]}

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value, (
        "a service actively crash-looping right now must still degrade the node"
    )


def test_a_non_autobot_service_with_a_high_restart_count_never_mattered():
    """Scope guard: only `autobot*` units are in play, restart count or not."""
    extra_data = {"discovered_services": [{"name": "sshd", "status": "running", "n_restarts": 50}]}

    assert _status(extra_data) == reconciler.NodeStatus.ONLINE.value


def test_high_metrics_still_win_over_a_clean_service_list():
    """The metric thresholds this fix must not touch."""
    assert (
        reconciler.ReconcilerService._calculate_node_status(SimpleNamespace(), 96.0, 0.0, 0.0, None)
        == reconciler.NodeStatus.ERROR.value
    )
    assert (
        reconciler.ReconcilerService._calculate_node_status(SimpleNamespace(), 85.0, 0.0, 0.0, None)
        == reconciler.NodeStatus.DEGRADED.value
    )


class _FakeSession:
    """Minimal async session for driving the real `update_node_heartbeat`.

    Only what this test's single node/heartbeat needs: one `Node` row returned
    on the first `select`, no-op `add`/`commit`/`refresh`. `extra_data` in this
    test carries no "discovered_services"/"services" payload for `_sync_
    discovered_services` to act on, so no further `Service` selects happen --
    keeping this fake to exactly what the code path under test executes.
    """

    def __init__(self, node):
        self._node = node

    async def execute(self, _query):
        return SimpleNamespace(scalar_one_or_none=lambda: self._node, scalars=lambda: SimpleNamespace(all=lambda: []))

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


def _degraded_node_with_resolved_crash_loop():
    """A node stuck exactly as this issue describes: DEGRADED, healthy heartbeat history."""
    return SimpleNamespace(
        node_id="node-14465",
        hostname="node-14465",
        status=reconciler.NodeStatus.DEGRADED.value,
        cpu_percent=0.0,
        memory_percent=0.0,
        disk_percent=0.0,
        last_heartbeat=datetime.now(timezone.utc),
        extra_data={},
        agent_version=None,
        os_info=None,
    )


def test_a_healthy_heartbeat_against_a_degraded_node_transitions_it_online():
    """AC: drive a healthy heartbeat against a degraded node, assert the transition.

    Not `_calculate_node_status` in isolation -- the full `update_node_heartbeat`
    path, matching the issue's own acceptance criterion verbatim. The service
    list is empty on THIS heartbeat (the resolved crash-loop is history, not
    something the current agent report still carries), which is exactly what
    lets it recompute ONLINE.
    """
    import asyncio

    node = _degraded_node_with_resolved_crash_loop()
    session = _FakeSession(node)
    service = reconciler.ReconcilerService()

    result = asyncio.run(
        service.update_node_heartbeat(
            session,
            node.node_id,
            _CPU,
            _MEM,
            _DISK,
            extra_data={},
        )
    )

    assert result is not None
    assert result.status == reconciler.NodeStatus.ONLINE.value, (
        "a healthy heartbeat against a degraded node did not transition it back to online"
    )
