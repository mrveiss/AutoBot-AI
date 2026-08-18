# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_restart_service_via_ansible` had no wall-clock timeout on its playbook run (#14524).

Three things this covers, each with its own discriminating test:

1. The escalation floor (`_effective_tracker_expiry_s`) now folds in
   `REMEDIATION_PLAYBOOK_TIMEOUT_S`. Pre-#14524 the margin was
   `max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S)`; the playbook run
   itself was unbounded and simply never appeared in the formula at all. Post-
   fix it is `max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S +
   REMEDIATION_PLAYBOOK_TIMEOUT_S)` -- the two waits inside one
   `_remediate_node` attempt are SEQUENTIAL (the ansible run, then, only if
   it succeeded, the heartbeat poll), so their sum is the real worst case.

2. `_restart_service_via_ansible` must actually PASS a concrete `timeout_s`
   to `execute_playbook` -- the constant existing is not the same as it being
   wired to the one call path that needed it (#14524's own repro: "Playbook
   run 241s+: 56 restarts / 0 escalations" happened with the constant space
   entirely unbounded, i.e. never reaching `execute_playbook` at all).

3. A timed-out run must fail the remediation, not read as success -- the
   silent-failure shape this repo keeps finding. `execute_playbook` returning
   `success=False` for a timeout must make `_restart_service_via_ansible`
   return `False`, exactly like any other failed run, so `_remediate_node`'s
   attempt counter advances toward escalation instead of resetting.

Loaded from disk like its `reconciler_remediation_tracker_expiry_14465_test.py`
sibling: the package conftest stubs `services.*`, and a plain import yields a
MagicMock that would pass every assertion here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
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
        "reconciler_under_playbook_timeout_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_playbook_timeout_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


def test_the_real_module_was_loaded_not_a_stub():
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert isinstance(reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S, int)
    assert reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S > 0


def test_effective_expiry_floor_sums_heartbeat_wait_and_playbook_timeout():
    """The primary #14524 discriminator on the escalation floor.

    Pre-#14524: `margin = max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S)`
    -- at the module defaults (reconcile_interval=60, HEARTBEAT_WAIT_S=90) that
    is 90, giving a floor of 391. Post-fix: margin also folds in
    `REMEDIATION_PLAYBOOK_TIMEOUT_S` (180 by default), giving 270 and a floor
    of 571. Asserting the exact new value fails outright against the old
    formula -- it would compute 391, not 571.
    """
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1  # force the settings-derived floor to be the binding one
    try:
        effective = reconciler._effective_tracker_expiry_s()
    finally:
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry

    expected = (
        reconciler.REMEDIATION_COOLDOWN
        + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
        + 1
    )
    assert effective == expected, f"expected {expected} (folding in the playbook timeout), got {effective}"


def test_restart_service_via_ansible_passes_the_playbook_timeout_through():
    """#14524's core wiring claim: the constant existing is not enough --
    `_restart_service_via_ansible` must hand it to `execute_playbook`.
    Pre-#14524 no `timeout_s` kwarg was passed at all, so the captured kwargs
    dict never contains one and this assertion fails on a `None` (`.get`
    default), not merely on a wrong number.
    """
    captured: dict = {}

    async def _fake_execute_playbook(**kwargs):
        captured.update(kwargs)
        return {"success": True, "output": "ok", "returncode": 0, "timed_out": False}

    fake_executor = MagicMock()
    fake_executor.execute_playbook = _fake_execute_playbook

    real_playbook_executor_module = sys.modules.get("services.playbook_executor")
    assert real_playbook_executor_module is not None, "services.playbook_executor must already be stubbed by conftest"
    original_getter = real_playbook_executor_module.get_playbook_executor
    real_playbook_executor_module.get_playbook_executor = lambda: fake_executor
    try:
        service = reconciler.ReconcilerService()
        result = asyncio.run(service._restart_service_via_ansible("node-14524", "slm-agent"))
    finally:
        real_playbook_executor_module.get_playbook_executor = original_getter

    assert result is True
    assert captured.get("timeout_s") == reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S, (
        f"expected timeout_s={reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S} to reach execute_playbook, "
        f"got {captured.get('timeout_s')!r} (captured kwargs: {sorted(captured)})"
    )


def test_restart_service_via_ansible_returns_false_on_a_timed_out_run():
    """A timeout must read as a FAILED restart, never a silent success.

    `execute_playbook` returning the shape a real timeout produces
    (`success=False`, `timed_out=True`, `returncode=-9`) must make
    `_restart_service_via_ansible` return `False` -- exactly what
    `_remediate_node` needs to advance its attempt counter instead of
    resetting it.
    """

    async def _fake_execute_playbook(**_kwargs):
        return {
            "success": False,
            "output": "[TIMEOUT] ansible-playbook killed after exceeding 180s wall-clock timeout (#14524)",
            "returncode": -9,
            "timed_out": True,
        }

    fake_executor = MagicMock()
    fake_executor.execute_playbook = _fake_execute_playbook

    real_playbook_executor_module = sys.modules.get("services.playbook_executor")
    original_getter = real_playbook_executor_module.get_playbook_executor
    real_playbook_executor_module.get_playbook_executor = lambda: fake_executor
    try:
        service = reconciler.ReconcilerService()
        result = asyncio.run(service._restart_service_via_ansible("node-14524", "slm-agent"))
    finally:
        real_playbook_executor_module.get_playbook_executor = original_getter

    assert result is False, "a timed-out playbook run must never be reported as a successful restart"


class _Clock:
    """A controllable stand-in for `datetime` inside `services.reconciler`.

    `advance` is used to fold SIMULATED wall-clock cost (e.g. a slow playbook
    run) into `last_attempt` bookkeeping without a real test actually
    sleeping -- same technique as
    `reconciler_remediation_tracker_expiry_14465_test.py`.
    """

    def __init__(self, start: datetime):
        self.current = start

    def now(self, _tz=None) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _FakeSession:
    def add(self, _obj):
        pass

    async def commit(self):
        pass


def _degraded_node() -> SimpleNamespace:
    return SimpleNamespace(node_id="node-14524", hostname="node-14524", ansible_target="node-14524")


def test_escalation_reachable_at_the_new_bounded_worst_case_playbook_duration():
    """Ties the floor change to real behaviour, at the worst case #14524 itself now allows.

    Simulates a node whose every restart consumes the FULL
    `REMEDIATION_PLAYBOOK_TIMEOUT_S` (a run that always hits the new bound)
    and then never heartbeats -- the worst-case single-attempt duration the
    new floor formula is sized for. `REMEDIATION_TRACKER_EXPIRY_S` is forced
    pathologically low (as the #14465 sibling test does) so the FLOOR, not
    the generous 1800s default, is what is actually exercised.

    Per cycle this model advances the clock by
    `REMEDIATION_PLAYBOOK_TIMEOUT_S` (180, inside the stubbed restart) plus
    `REMEDIATION_COOLDOWN + 5` (305, modelling the reconcile loop noticing
    the cooldown cleared) = 485s between one `last_attempt` and the next.

    Discriminates cleanly against the pre-#14524 margin
    (`max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S)`, floor 391 at
    the module defaults): 391 < 485, so the OLD floor forgives every cycle --
    count resets to 0 each time and escalation is UNREACHABLE, the exact "56
    restarts / 0 escalations" shape #14524 reports. The NEW floor (571,
    391 + REMEDIATION_PLAYBOOK_TIMEOUT_S) exceeds 485, so it does not.
    """
    service = reconciler.ReconcilerService()
    clock = _Clock(datetime.now(timezone.utc))

    async def _slow_restart(*_args, **_kwargs):
        # Models the newly-BOUNDED worst case: the playbook consumes exactly
        # its ceiling before failing.
        clock.advance(reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S)
        return False  # a timed-out run always reports failure (this issue's #3)

    service._restart_service_via_ansible = _slow_restart
    heartbeat_calls = {"count": 0}

    async def _unreachable_heartbeat(*_args, **_kwargs):
        heartbeat_calls["count"] += 1
        return False

    service._heartbeat_returned = _unreachable_heartbeat

    reconciler.datetime = clock
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1  # force the floor, not the 1800s default, to be binding
    try:
        db = _FakeSession()
        node = _degraded_node()
        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            # Models the reconcile loop noticing the cooldown cleared.
            clock.advance(reconciler.REMEDIATION_COOLDOWN + 5)
    finally:
        reconciler.datetime = datetime
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS
    assert tracker.get("exhausted") is True, f"escalation failed even at the new bounded worst case -- got {tracker}"
    # `_restart_service_via_ansible` returning False short-circuits `restarted
    # and await self._heartbeat_returned(...)` -- the heartbeat wait must
    # never even be reached for a failed restart.
    assert heartbeat_calls["count"] == 0, "_heartbeat_returned must not be polled when the restart itself failed"
