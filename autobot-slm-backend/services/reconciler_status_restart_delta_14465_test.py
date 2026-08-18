# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node stays degraded forever while heartbeating healthily (#14465, defect 1).

`_calculate_node_status` degraded on `n_restarts > 3` -- systemd's `NRestarts`
property, read in `health_collector._get_service_details` -- treated as a
static absolute threshold. `NRestarts` climbs for as long as a unit keeps
failing (systemd resets it on the next clean manual start once a unit settles,
not merely with the passage of time), so a static gate on it can climb past 3
and never come back down on its own: once any managed service anywhere in a
node's uptime crossed 3 restarts, every future heartbeat computed DEGRADED
regardless of current metrics or the service's current state.

Review found regressions in two earlier versions of this fix:

1. Dropping `n_restarts > 3` in favour of `status == "failed"` alone lost the
   CHURNING shape -- a service restarting faster than the heartbeat samples
   it reads `"running"` on most samples and never reaches `"failed"` while it
   is actively unstable.
2. The restored `status == "failed"` check, scoped to `extra_data["services"]`
   (`slm_services_to_monitor`), is dark on most of a fleet: that operator
   -declared set is `[]` by role default, `[]` on at least one real inventory
   node, and never contains `slm-agent`.
3. A THIRD round replaced the absolute threshold with a bare DELTA ("did
   `n_restarts` rise since the immediately preceding heartbeat") -- still a
   regression, just subtler: `health_collector`'s own service-discovery sweep
   is cached for 300s against a 30s heartbeat, so 9 of every 10 beats carry a
   byte-identical cached snapshot. Measured: 1 of 20 beats degraded across
   continuous churn, and the node flapped ONLINE/DEGRADED every 5 minutes
   instead of staying DEGRADED. A pulse tells you an increase happened; a
   level tells you the node is CURRENTLY churning, which is what a status
   field means.

This fix (`_restart_churn_active`) persists the TIMESTAMP of the last observed
increase and reports churning while `now - last_increase < RESTART_CHURN_
WINDOW_S` -- a level, comfortably larger than the 300s discovery cache TTL --
kept alongside `status == "failed"` for the shape that has already settled and
stopped restarting altogether (a level still goes quiet once `NRestarts` stops
climbing for long enough; only the CURRENT status string catches "stayed
dead"). Both signals are scoped by `is_managed_autobot_service`
(`services/service_extra_data.py`): `autobot*`-prefixed or `slm-agent` itself,
NOT explicitly disabled in systemd -- not `enabled` alone (which excludes
`static`/`indirect`/`enabled-runtime`/`generated`/`alias`, invisible-forever
units like `autobot-key-rotation`/`autobot-pg-backup`), and not the
monitored-services list.

The module is loaded from disk, not imported, because the package conftest
stubs `services.*` and a plain `import services.reconciler` yields a
MagicMock that would satisfy every check here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from datetime import datetime, timedelta, timezone
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


def _status(extra_data=None, restart_churn_active=False) -> str:
    """Call the real `_calculate_node_status` -- it does not touch `self`."""
    return reconciler.ReconcilerService._calculate_node_status(
        SimpleNamespace(), _CPU, _MEM, _DISK, extra_data, restart_churn_active
    )


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.isfunction(reconciler.ReconcilerService._calculate_node_status)
    assert inspect.isfunction(reconciler.ReconcilerService._update_existing_service)


def test_a_service_that_restarted_long_ago_but_is_now_running_is_not_degraded():
    """The original defect, reproduced directly.

    `autobot-vnc` crossed several restarts at some point in the node's uptime
    and is presently `status: "running"` with no active churn this heartbeat.
    Healthy metrics, no active instability: this must be ONLINE.
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-vnc", "status": "running", "n_restarts": 5, "unit_file_state": "static"}
        ]
    }

    assert _status(extra_data, restart_churn_active=False) == reconciler.NodeStatus.ONLINE.value, (
        "a service with an old, non-advancing restart count pinned the node DEGRADED forever (#14465)"
    )


def test_a_settled_failed_service_still_degrades_with_no_active_churn():
    """The shape a churn window alone would eventually miss: `NRestarts`
    stopped climbing because systemd's own `StartLimitBurst`/
    `StartLimitIntervalSec` (#4090) gave up and parked the unit at `"failed"`
    -- its designed end state for a real, sustained crash loop, not
    `"crash-loop"` (`_map_status_from_states` never maps to that string for
    `failed`).
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-vnc", "status": "failed", "n_restarts": 8, "unit_file_state": "static"}
        ]
    }

    assert _status(extra_data, restart_churn_active=False) == reconciler.NodeStatus.DEGRADED.value


def test_a_presently_crash_looping_service_still_degrades_the_node():
    """Issue #1604's actual intent must survive this fix.

    `status == "crash-loop"` reflects systemd's `activating`+`auto-restart`
    sub-state -- true only while the unit is presently churning right at
    sample time.
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-vnc", "status": "crash-loop", "n_restarts": 1, "unit_file_state": "static"}
        ]
    }

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value


def test_slm_agent_itself_is_in_scope():
    """#14465 review: `slm-agent` never matches `startswith("autobot")`, and it
    is the one unit remediation actually restarts. It must not be permanently
    excluded from every degrade signal just because of its name.
    """
    extra_data = {
        "discovered_services": [
            {"name": "slm-agent", "status": "failed", "n_restarts": 4, "unit_file_state": "enabled"}
        ]
    }

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value


def test_a_static_unit_with_no_install_section_is_still_in_scope():
    """Review: `UnitFileState == "enabled"` alone excludes `static` units --
    `autobot-key-rotation.service.j2`/`autobot-pg-backup.service.j2` have no
    `[Install]` section and are `static` forever. Gating on "not explicitly
    disabled" instead must still catch a `static` unit that is `"failed"`.
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-key-rotation", "status": "failed", "n_restarts": 1, "unit_file_state": "static"}
        ]
    }

    assert _status(extra_data) == reconciler.NodeStatus.DEGRADED.value


def test_an_explicitly_disabled_unit_never_false_positives():
    """#1709, restated against the new scope.

    `autobot-vnc` failed on a node where VNC was never installed
    (`install_vnc` unset, so the unit stays `UnitFileState: "disabled"`) must
    not degrade the node -- exactly the false positive #1709 existed to
    prevent, now derived from "not explicitly disabled" rather than a
    monitored-services list or an `enabled`-only gate.
    """
    extra_data = {
        "discovered_services": [
            {"name": "autobot-vnc", "status": "failed", "n_restarts": 1, "unit_file_state": "disabled"}
        ]
    }

    assert _status(extra_data) == reconciler.NodeStatus.ONLINE.value


def test_a_non_autobot_service_never_mattered_regardless_of_state():
    """Scope guard: only managed autobot/slm-agent units are in play."""
    extra_data = {
        "discovered_services": [
            {"name": "sshd", "status": "failed", "n_restarts": 50, "unit_file_state": "enabled"}
        ]
    }

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


# ---------------------------------------------------------------------------
# `_restart_churn_active` / `_update_existing_service` executed directly.
#
# Review: the churn signal being TRUE or FALSE is not itself interesting to
# assert on in isolation -- passing `restart_churn_active=True` straight into
# `_calculate_node_status` only exercises `_service_health_degraded`'s first
# `if`, which is true by construction. What must be tested is whether the
# REAL computation (against a real, persisted previous row) produces that
# value in the first place. These tests call the real, module-level
# `_restart_churn_active` and the real `_update_existing_service`.
# ---------------------------------------------------------------------------


def test_a_fresh_increase_arms_the_churn_window():
    """Discriminates directly against the deleted `n_restarts > 3` branch AND
    against a bare pulse: `n_restarts: 1` (up from a stored 0) would never
    have tripped `n_restarts > 3` on `origin/Dev_new_gui`, and the real
    `_restart_churn_active` -- not a hand-fed boolean -- is what must detect
    the rise.
    """
    svc_data = {"name": "autobot-vnc", "status": "running", "n_restarts": 1, "unit_file_state": "static"}
    now = datetime.now(timezone.utc)

    churning, last_increase_iso = reconciler._restart_churn_active(svc_data, {"n_restarts": 0}, now)

    assert churning is True, "a fresh restart must arm the churn window, not wait for an arbitrary absolute count"
    assert last_increase_iso is not None


def test_a_second_consecutive_beat_with_an_unchanged_count_still_reports_churning():
    """The level/pulse distinction itself -- one of the two tests review named
    as missing. A service armed the window on a prior beat; THIS beat shows
    no new increase (the discovery cache had not refreshed). Under the
    deleted pulse design this would report `False`; the level must still
    report `True` while within `RESTART_CHURN_WINDOW_S`, and must NOT re-arm
    the window with a fresh timestamp on a beat that added nothing new.
    """
    t0 = datetime.now(timezone.utc)
    armed_svc = {"name": "autobot-vnc", "status": "running", "n_restarts": 10, "unit_file_state": "static"}
    churning_t0, last_increase_t0 = reconciler._restart_churn_active(armed_svc, {"n_restarts": 5}, t0)
    assert churning_t0 is True, "sanity: the first beat must arm the window"

    t1 = t0 + timedelta(seconds=30)
    unchanged_svc = {"name": "autobot-vnc", "status": "running", "n_restarts": 10, "unit_file_state": "static"}
    previous_extra = {"n_restarts": 10, "n_restarts_increased_at": last_increase_t0}
    churning_t1, last_increase_t1 = reconciler._restart_churn_active(unchanged_svc, previous_extra, t1)

    assert churning_t1 is True, "an unchanged count must still report churning while inside the armed window"
    assert last_increase_t1 == last_increase_t0, "an unchanged count must not re-arm the window with a new timestamp"


def test_the_churn_window_eventually_closes_for_a_single_benign_restart():
    """A single restart (an OOM kill, a dependency flap) must not degrade the
    node forever -- only for `RESTART_CHURN_WINDOW_S`. This is the trade this
    fix makes explicit in place of the absolute threshold's unbounded one.
    """
    t0 = datetime.now(timezone.utc)
    svc_data = {"name": "autobot-vnc", "status": "running", "n_restarts": 10, "unit_file_state": "static"}
    _, last_increase = reconciler._restart_churn_active(svc_data, {"n_restarts": 5}, t0)

    far_future = t0 + timedelta(seconds=reconciler.RESTART_CHURN_WINDOW_S + 30)
    previous_extra = {"n_restarts": 10, "n_restarts_increased_at": last_increase}
    still_churning, _ = reconciler._restart_churn_active(svc_data, previous_extra, far_future)

    assert still_churning is False, "the churn window must close -- a single restart cannot degrade the node forever"


def test_a_churning_payload_with_no_prior_row_does_not_fabricate_a_signal():
    """The second test review named as missing: first-ever observation (a
    node registering, a row `_remove_stale_services` deleted and the agent
    re-reported, or a restored manager DB) genuinely has no rate information.
    Honestly reports "not churning" rather than guessing -- the accepted
    trade-off for a LEVEL signal (the next real increase arms the window),
    unlike a static absolute threshold which had no such excuse.
    """
    svc_data = {"name": "autobot-vnc", "status": "running", "n_restarts": 47, "unit_file_state": "static"}

    churning, last_increase_iso = reconciler._restart_churn_active(svc_data, {}, datetime.now(timezone.utc))

    assert churning is False
    assert last_increase_iso is None


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
    seeded `_ServiceRow`, taking the update path where the churn signal lives.
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
    """The full path, not `_calculate_node_status` or `_restart_churn_active`
    in isolation.

    A `Service` row already on record from a PRIOR heartbeat shows
    `n_restarts: 44`. This heartbeat reports `n_restarts: 47`, still
    `"running"` -- the review's original counter-example -- and must
    transition the node to DEGRADED because `_update_existing_service`
    detects the rise against that prior row, through the real
    `update_node_heartbeat` -> `_update_node_metrics` ->
    `_sync_discovered_services` -> `_upsert_service` ->
    `_calculate_node_status` chain, and persists the churn timestamp for the
    NEXT heartbeat to read.
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
        "discovered_services": [
            {"name": "autobot-vnc", "status": "running", "n_restarts": 47, "unit_file_state": "static"}
        ]
    }

    result = asyncio.run(service.update_node_heartbeat(session, node.node_id, _CPU, _MEM, _DISK, extra_data=this_beat))

    assert result.status == reconciler.NodeStatus.DEGRADED.value, (
        "n_restarts rising from 44 to 47 against the prior heartbeat's row did not degrade the node"
    )
    assert seeded_service.extra_data.get("n_restarts") == 47, "the new count must be persisted for the NEXT heartbeat"
    assert seeded_service.extra_data.get("n_restarts_increased_at") is not None, (
        "the churn-arming timestamp must be persisted so the NEXT heartbeat can still report churning "
        "even without a further increase (the pulse-to-level fix's whole point)"
    )
