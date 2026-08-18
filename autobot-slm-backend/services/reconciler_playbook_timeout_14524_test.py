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

    `timeout_s` is now a REQUIRED parameter of `_restart_service_via_ansible`
    itself (review, round 2): reusing one bound for both call paths meant the
    slm-agent-sized `REMEDIATION_PLAYBOOK_TIMEOUT_S` also bounded
    `_remediate_failed_service`'s restart of an arbitrary
    `ServiceCategory.AUTOBOT` unit, which can be a `Type=oneshot` job with a
    multi-minute `TimeoutStartSec`. This test passes
    `REMEDIATION_PLAYBOOK_TIMEOUT_S` explicitly, exactly as `_remediate_node`
    does; the sibling test below covers `_remediate_failed_service`'s own,
    much larger budget.
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
        result = asyncio.run(
            service._restart_service_via_ansible(
                "node-14524", "slm-agent", timeout_s=reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
            )
        )
    finally:
        real_playbook_executor_module.get_playbook_executor = original_getter

    assert result is True
    assert captured.get("timeout_s") == reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S, (
        f"expected timeout_s={reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S} to reach execute_playbook, "
        f"got {captured.get('timeout_s')!r} (captured kwargs: {sorted(captured)})"
    )


def test_remediate_failed_service_uses_its_own_much_larger_playbook_timeout():
    """High-severity review finding, round 2: the two callers of
    `_restart_service_via_ansible` restart very different shapes of unit.
    `_remediate_node` always restarts the lightweight `slm-agent`; but
    `_remediate_failed_service` restarts an arbitrary `ServiceCategory.AUTOBOT`
    unit, which `AUTOBOT_SERVICE_PATTERNS` (service_categorizer.py) matches by
    NAME PREFIX (postgresql*, redis*, docker*, ...) -- an open-ended set that
    includes `Type=oneshot` jobs with a multi-minute `TimeoutStartSec`
    (`autobot-pg-backup.service.j2` declares 1800s). Reusing the slm-agent
    budget (180s) here would SIGKILL a legitimate long-running restart.

    Discriminates: before this fix both call paths shared ONE hardcoded
    `REMEDIATION_PLAYBOOK_TIMEOUT_S`, so this assertion would see 180, not
    `SERVICE_RESTART_PLAYBOOK_TIMEOUT_S` (2100 by default) -- a real,
    order-of-magnitude difference, not a coincidental match.
    """
    captured: dict = {}

    async def _fake_execute_playbook(**kwargs):
        captured.update(kwargs)
        return {"success": True, "output": "ok", "returncode": 0, "timed_out": False}

    fake_executor = MagicMock()
    fake_executor.execute_playbook = _fake_execute_playbook

    real_playbook_executor_module = sys.modules.get("services.playbook_executor")
    original_getter = real_playbook_executor_module.get_playbook_executor
    real_playbook_executor_module.get_playbook_executor = lambda: fake_executor
    try:
        service = reconciler.ReconcilerService()
        node = SimpleNamespace(node_id="node-14524", hostname="node-14524", ansible_target="node-14524")
        service_row = SimpleNamespace(service_name="autobot-pg-backup")
        db = _FakeSession()
        result = asyncio.run(service._remediate_failed_service(db, node, service_row))
    finally:
        real_playbook_executor_module.get_playbook_executor = original_getter

    assert result is True
    assert reconciler.SERVICE_RESTART_PLAYBOOK_TIMEOUT_S > reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S, (
        "the service-restart budget must be the LARGER of the two for this test to mean anything"
    )
    assert captured.get("timeout_s") == reconciler.SERVICE_RESTART_PLAYBOOK_TIMEOUT_S, (
        f"expected the service-restart path to use SERVICE_RESTART_PLAYBOOK_TIMEOUT_S="
        f"{reconciler.SERVICE_RESTART_PLAYBOOK_TIMEOUT_S}, got {captured.get('timeout_s')!r} "
        f"(captured kwargs: {sorted(captured)})"
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
        result = asyncio.run(
            service._restart_service_via_ansible(
                "node-14524", "slm-agent", timeout_s=reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
            )
        )
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


def _gap_after_one_attempt(work_duration_s: int) -> int:
    """The REAL wall-clock gap one `_remediate_node` attempt leaves before the
    next real attempt can fire, given `work_duration_s` of simulated work.

    `last_attempt` is stamped at attempt START (`now`, captured before any
    restart/heartbeat work runs) -- review, round 2: an earlier version of
    this test advanced the clock by a full extra `REMEDIATION_COOLDOWN` AFTER
    every cycle, DOUBLE-COUNTING the cooldown against the work already
    elapsed inside the SAME attempt (real gap ~330-360s, not the ~485s that
    version computed). The correct model: cooldown only needs whatever is
    LEFT after `work_duration_s` has already elapsed against it
    (`max(0, REMEDIATION_COOLDOWN - work_duration_s)`), plus one
    reconcile-interval poll's worth of slack for the loop to notice.
    """
    remaining_cooldown = max(0, reconciler.REMEDIATION_COOLDOWN - work_duration_s)
    return work_duration_s + remaining_cooldown + 60  # 60 == reconcile_interval fallback (getattr default)


def test_escalation_reachable_at_the_shipped_default_because_the_timeout_bounds_the_run():
    """The actual fix for the reported "56 restarts / 0 escalations" shape, at
    the SHIPPED default (review, round 2 -- correcting an earlier version of
    this test's over-stated claim).

    At `REMEDIATION_PLAYBOOK_TIMEOUT_S=180`, `work_duration =
    REMEDIATION_PLAYBOOK_TIMEOUT_S + REMEDIATION_HEARTBEAT_WAIT_S = 270s`,
    which is UNDER `REMEDIATION_COOLDOWN` (300s) -- so the resulting real gap
    (`_gap_after_one_attempt(270)` = 360s) is already covered by the
    PRE-#14524 margin too (floor 391s > 360s). What actually closes the
    reported bug at these defaults is bounding `execute_playbook` AT ALL: pre-
    #14524 that run was UNBOUNDED, so `work_duration` (and therefore the real
    gap) could grow arbitrarily large and eventually exceed ANY finite floor,
    no matter how it was computed. The floor formula change is a separate,
    defensive improvement -- see the sibling test below for the scenario
    where IT, specifically, is what matters.
    """
    service = reconciler.ReconcilerService()
    clock = _Clock(datetime.now(timezone.utc))

    async def _bounded_but_successful_restart(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S)
        return True  # the run itself succeeds -- heartbeat is what never verifies

    async def _never_verifies(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_HEARTBEAT_WAIT_S)
        return False

    service._restart_service_via_ansible = _bounded_but_successful_restart
    service._heartbeat_returned = _never_verifies

    reconciler.datetime = clock
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1  # force the floor, not the 1800s default, to be binding
    try:
        db = _FakeSession()
        node = _degraded_node()
        work_duration = reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        outer_advance = _gap_after_one_attempt(work_duration) - work_duration
        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(outer_advance)
    finally:
        reconciler.datetime = datetime
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS
    assert tracker.get("exhausted") is True, f"escalation failed at the shipped default -- got {tracker}"


def test_floor_extension_matters_once_an_operator_raises_the_playbook_timeout():
    """The scenario where the #14524 floor extension, specifically, is load-bearing.

    Review, round 2: "the bump is harmless and future-proofs a raised
    timeout, but it is not what fixes the 56/0 repro -- the timeout is."
    Honoured here by finding the scenario where the bump DOES matter and
    testing that one directly, instead of letting the default-value test
    above imply credit it cannot support.

    `REMEDIATION_PLAYBOOK_TIMEOUT_S` is raised (in-test only) to 280 --
    `work_duration = 280 + 90 = 370s`, over `REMEDIATION_COOLDOWN` (300s), so
    the real gap (`_gap_after_one_attempt(370)` = 430s) exceeds the OLD
    margin's floor (391s, `REMEDIATION_HEARTBEAT_WAIT_S` alone) -- forgiven
    every cycle, escalation unreachable. The NEW margin folds in the raised
    timeout too (floor 671s) and does not forgive.
    """
    service = reconciler.ReconcilerService()
    clock = _Clock(datetime.now(timezone.utc))

    original_playbook_timeout = reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
    reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S = 280
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1

    async def _slow_but_successful_restart(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S)
        return True

    async def _never_verifies(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_HEARTBEAT_WAIT_S)
        return False

    service._restart_service_via_ansible = _slow_but_successful_restart
    service._heartbeat_returned = _never_verifies

    reconciler.datetime = clock
    try:
        db = _FakeSession()
        node = _degraded_node()
        work_duration = reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        outer_advance = _gap_after_one_attempt(work_duration) - work_duration
        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(outer_advance)
    finally:
        reconciler.datetime = datetime
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry
        reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S = original_playbook_timeout

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS
    assert tracker.get("exhausted") is True, (
        f"escalation failed once the playbook timeout was raised past the pre-#14524 margin -- got {tracker}"
    )
