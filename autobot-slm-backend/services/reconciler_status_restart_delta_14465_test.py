# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node stays degraded forever while heartbeating healthily (#14465, defect 1).

`_calculate_node_status` degraded on `n_restarts > 3` -- systemd's `NRestarts`
property, read in `health_collector._get_service_details` -- treated as a
static absolute threshold. `NRestarts` is lifetime-cumulative: systemd never
resets it except at reboot or `systemctl reset-failed`. Used as a static gate,
it can only ever climb: once any managed service anywhere in a node's uptime
crossed 3 restarts, every future heartbeat computed DEGRADED regardless of
current metrics or the service's current state, with no path back to ONLINE.

Review of two earlier versions of this fix found real regressions:

1. Dropping `n_restarts > 3` in favour of `status == "failed"` alone lost the
   CHURNING shape -- a service restarting faster than the heartbeat samples
   it (`RestartSec` typically well under the heartbeat interval) reads
   `"running"` on most samples and never reaches `"failed"` at all while it
   is actively unstable.
2. The restored `status == "failed"` check, scoped to `extra_data["services"]`
   (`slm_services_to_monitor`), is dark on most of a fleet: that operator
   -declared set is `[]` by role default, `[]` on at least one real inventory
   node, and never contains `slm-agent` -- the one unit remediation actually
   restarts.

This fix replaces the absolute threshold with a DELTA -- `n_restarts` rising
since the immediately preceding heartbeat, persisted per service on
`Service.extra_data` -- which catches the churning shape without needing any
single sample to land on a particular status string, kept alongside
`status == "failed"` for the shape that has already settled and stopped
restarting altogether (a delta alone goes quiet the moment `NRestarts` stops
climbing). Both are scoped by `is_managed_autobot_service`
(`services/service_extra_data.py`): `autobot*`-prefixed or `slm-agent` itself,
AND systemd-`enabled` on this node -- not the monitored-services list.

The module is loaded from disk, not imported, because the package conftest
stubs `services.*` and a plain `import services.reconciler` yields a
MagicMock that would satisfy every check here while exercising nothing.
"""

from __future__ import annotations

import asyncio
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
        "reconciler_under_delta_status_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_delta_status_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()

# Healthy metrics straight from the issue's evidence.
_CPU, _MEM, _DISK = 0.0, 23.4, 18.1


def _status(extra_data=None, restart_increase_detected=False) -> str:
    """Call the real `_calculate_node_status` -- it does not touch `self`."""
    return reconciler.ReconcilerService._calculate_node_status(
        SimpleNamespace(), _CPU, _MEM, _DISK, extra_data, restart_increase_detected
    )


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.isfunction(reconciler.ReconcilerService._calculate_node_status)


def test_a_service_that_restarted_long_ago_but_is_now_running_is_not_degraded():
    """The original defect, reproduced directly.

    `autobot-vnc` crossed several restarts at some point in the node's uptime
    and is presently `status: "running"` with NO fresh delta this heartbeat.
    Healthy metrics, no active instability: this must be ONLINE.
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "running", "n_restarts": 5, "enabled": True}]
    }

    assert _status(extra_data, restart_increase_detected=False) == reconciler.NodeStatus.ONLINE.value, (
        "a service with an old, non-advancing restart count pinned the node DEGRADED forever (#14465)"
    )


def test_a_churning_service_degrades_via_the_restart_delta_not_an_absolute():
    """Review's exact counter-example: `{"status": "running", "n_restarts": 47}`.

    A slow-churning service samples as "running" on most heartbeats
    (RestartSec well under the heartbeat interval) and would never trip a
    `status == "failed"`-only check. The delta -- computed elsewhere, against
    the previous heartbeat's stored value, and passed in here -- is what must
    degrade the node, independent of the absolute `n_restarts` value.
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "running", "n_restarts": 47, "enabled": True}]
    }

    assert _status(extra_data, restart_increase_detected=True) == reconciler.NodeStatus.DEGRADED.value


def test_a_single_fresh_restart_degrades_even_below_the_old_absolute_threshold():
    """Discriminates directly against the deleted `n_restarts > 3` branch.

    `n_restarts: 1` would never have tripped `n_restarts > 3` on `origin/
    Dev_new_gui` no matter what `restart_increase_detected` says -- this
    fails against that code path and passes only against the delta-based one.
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "running", "n_restarts": 1, "enabled": True}]
    }

    assert _status(extra_data, restart_increase_detected=True) == reconciler.NodeStatus.DEGRADED.value, (
        "a fresh restart must degrade immediately, not wait for an arbitrary absolute count"
    )


def test_a_settled_failed_service_still_degrades_with_no_fresh_delta():
    """The shape a delta alone would miss: `NRestarts` stopped climbing because
    systemd's own `StartLimitBurst`/`StartLimitIntervalSec` (#4090) gave up and
    parked the unit at `"failed"` -- its designed end state for a real,
    sustained crash loop, not `"crash-loop"` (`_map_status_from_states` never
    maps to that string for `failed`).
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "failed", "n_restarts": 8, "enabled": True}]
    }

    assert _status(extra_data, restart_increase_detected=False) == reconciler.NodeStatus.DEGRADED.value


def test_a_presently_crash_looping_service_still_degrades_the_node():
    """Issue #1604's actual intent must survive this fix.

    `status == "crash-loop"` reflects systemd's `activating`+`auto-restart`
    sub-state -- true only while the unit is presently churning right at
    sample time.
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "crash-loop", "n_restarts": 1, "enabled": True}]
    }

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value


def test_slm_agent_itself_is_in_scope():
    """#14465 review: `slm-agent` never matches `startswith("autobot")`, and it
    is the one unit remediation actually restarts. It must not be permanently
    excluded from every degrade signal just because of its name.
    """
    extra_data = {"discovered_services": [{"name": "slm-agent", "status": "failed", "n_restarts": 4, "enabled": True}]}

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value


def test_a_disabled_non_primary_autobot_unit_never_false_positives():
    """#1709, restated against the new scope.

    `autobot-vnc` failed on a node where VNC was never installed
    (`install_vnc` unset, so the unit stays `enabled: false`) must not
    degrade the node -- exactly the false positive #1709 existed to prevent,
    now derived from `enabled` rather than a monitored-services list.
    """
    extra_data = {
        "discovered_services": [{"name": "autobot-vnc", "status": "failed", "n_restarts": 1, "enabled": False}]
    }

    assert _status(extra_data) == reconciler.NodeStatus.ONLINE.value


def test_a_non_autobot_service_never_mattered_regardless_of_state():
    """Scope guard: only managed autobot/slm-agent units are in play."""
    extra_data = {"discovered_services": [{"name": "sshd", "status": "failed", "n_restarts": 50, "enabled": True}]}

    assert _status(extra_data) == reconciler.NodeStatus.ONLINE.value


def test_high_metrics_still_win_over_a_clean_service_list():
    """The metric thresholds this fix must not touch."""
    assert _status(None) == reconciler.NodeStatus.ONLINE.value
    assert (
        reconciler.ReconcilerService._calculate_node_status(SimpleNamespace(), 96.0, 0.0, 0.0, None, False)
        == reconciler.NodeStatus.ERROR.value
    )
    assert (
        reconciler.ReconcilerService._calculate_node_status(SimpleNamespace(), 85.0, 0.0, 0.0, None, False)
        == reconciler.NodeStatus.DEGRADED.value
    )


class _ServiceRow:
    """A stand-in `Service` ORM row -- only what `_update_existing_service` reads/writes.

    `models.database.Service` is a stubbed `MagicMock` under the package
    conftest, so a `Service(**kwargs)` constructor call (`_create_new_service`)
    would not actually set attributes matching those kwargs on its return
    value -- this fixture is used in place of that construction step, seeded
    directly as the "previous heartbeat" row, so the update (not create) path
    under test -- `_update_existing_service` -- runs against real data.
    """

    def __init__(self, extra_data=None):
        self.status = None
        self.active_state = None
        self.sub_state = None
        self.main_pid = None
        self.memory_bytes = None
        self.enabled = False
        self.description = None
        self.last_checked = None
        self.extra_data = extra_data or {}


class _SeededServiceHeartbeatSession:
    """Drives `update_node_heartbeat` with ONE pre-seeded existing `Service` row.

    The FIRST `execute()` is `_find_node_by_id_or_hostname`'s node lookup.
    The SECOND is `_upsert_service`'s existing-row lookup -- returns the
    seeded `_ServiceRow`, taking the update path where the delta lives.
    Every later call (`_remove_stale_services`'s stale-service scan) resolves
    to "nothing found".
    """

    def __init__(self, node, seeded_service: _ServiceRow):
        self._node = node
        self._seeded_service = seeded_service
        self._reads = 0

    async def execute(self, _query):
        self._reads += 1
        if self._reads == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self._node)
        if self._reads == 2:
            return SimpleNamespace(scalar_one_or_none=lambda: self._seeded_service)
        return SimpleNamespace(scalar_one_or_none=lambda: None, scalars=lambda: SimpleNamespace(all=lambda: []))

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


def test_a_churning_service_degrades_across_a_real_heartbeat_against_its_prior_row():
    """The full path, not `_calculate_node_status` in isolation.

    A `Service` row already on record from a PRIOR heartbeat shows
    `n_restarts: 44`. This heartbeat reports `n_restarts: 47`, still
    `"running"` -- the exact review counter-example -- and must transition
    the node to DEGRADED because `_update_existing_service` detects the rise
    against that prior row, through the real `update_node_heartbeat` ->
    `_update_node_metrics` -> `_sync_discovered_services` ->
    `_upsert_service` -> `_calculate_node_status` chain.
    """
    node = SimpleNamespace(
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
    seeded_service = _ServiceRow(extra_data={"n_restarts": 44})
    session = _SeededServiceHeartbeatSession(node, seeded_service)
    service = reconciler.ReconcilerService()

    this_beat = {
        "discovered_services": [{"name": "autobot-vnc", "status": "running", "n_restarts": 47, "enabled": True}]
    }

    result = asyncio.run(service.update_node_heartbeat(session, node.node_id, _CPU, _MEM, _DISK, extra_data=this_beat))

    assert result.status == reconciler.NodeStatus.DEGRADED.value, (
        "n_restarts rising from 44 to 47 against the prior heartbeat's row did not degrade the node"
    )
    assert seeded_service.extra_data.get("n_restarts") == 47, "the new count must be persisted for the NEXT heartbeat"
