# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_restart_service_via_ansible` had no wall-clock timeout on its playbook run (#14524).

Three things this covers, each with its own discriminating test:

1. The escalation floor (`_effective_tracker_expiry_s`) now folds in
   `REMEDIATION_PLAYBOOK_TIMEOUT_S` AND `_update_code_source_worst_case_s()`
   (review, round 3 -- `execute_playbook` runs `_update_code_source()` before
   `_run_subprocess`, as part of the SAME attempt). Pre-#14524 the margin was
   `max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S)`; the playbook run
   (and the git sync before it) were unbounded and simply never appeared in
   the formula at all. Post-fix it is `max(reconcile_interval,
   update_code_source_worst_case + REMEDIATION_HEARTBEAT_WAIT_S +
   REMEDIATION_PLAYBOOK_TIMEOUT_S)` -- all three phases inside one
   `_remediate_node` attempt are SEQUENTIAL (the git sync, then the ansible
   run, then, only if it succeeded, the heartbeat poll), so their sum is the
   real worst case.

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
import math
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
    -- at the module defaults (reconcile_interval=60, HEARTBEAT_WAIT_S=90)
    that is 90, giving a floor of 391. Post-fix (round 3): margin also folds
    in `REMEDIATION_PLAYBOOK_TIMEOUT_S` (180) AND
    `_update_code_source_worst_case_s()` (180 at defaults, whether read from
    the real `playbook_executor` module or this function's own documented
    fallback -- both agree at these defaults), giving 450 and a floor of 751.
    Asserting the exact new value fails outright against either the
    round-1 (391) or round-2 (571) formula -- neither computes 751.

    `expected` is derived from `_update_code_source_worst_case_s()`'s ACTUAL
    return value (not a bare 180) so this test passes whichever of the
    fallback/real-import paths fires in a given test session -- see the two
    dedicated tests below for which path fires when.
    """
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    try:
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1  # force the settings-derived floor to be the binding one
        effective = reconciler._effective_tracker_expiry_s()
        update_code_source_worst_case = reconciler._update_code_source_worst_case_s()
    finally:
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry

    single_node_attempt_ceiling_s = (
        update_code_source_worst_case
        + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
    )
    expected = reconciler.REMEDIATION_COOLDOWN + math.ceil(single_node_attempt_ceiling_s) + 1
    assert effective == expected, f"expected {expected}, got {effective}"
    assert expected == 751, (
        f"expected update_code_source_worst_case ({update_code_source_worst_case}) to still resolve to the "
        f"documented 180s at these defaults -- got a floor of {expected}, not 751"
    )


def test_update_code_source_worst_case_s_falls_back_when_playbook_executor_unavailable():
    """`services.playbook_executor` resolves to the conftest MagicMock stub in
    this test's own session (it is derived into `_CODE_SYNC_SERVICE_MODULES`,
    not the real-loaded allowlist) -- `_update_code_source_worst_case_s()`
    must fall back to its documented 180.0, not silently propagate a
    MagicMock into `_effective_tracker_expiry_s()`'s arithmetic (which would
    raise `TypeError` one call later, not never, exactly the failure mode
    `_effective_tracker_expiry_s`'s OWN `reconcile_interval` guard already
    exists to avoid for a different attribute).
    """
    stub = sys.modules.get("services.playbook_executor")
    assert stub is not None, "services.playbook_executor must already be stubbed by conftest"
    # A MagicMock's attribute access always succeeds and returns another
    # MagicMock -- confirms the PRECONDITION this test is named for, rather
    # than assuming it.
    assert not isinstance(stub.update_code_source_worst_case_s(), (int, float))

    worst_case = reconciler._update_code_source_worst_case_s()
    assert worst_case == 180.0, f"expected the documented fallback (180.0), got {worst_case!r}"


def test_update_code_source_worst_case_s_reads_the_real_function_when_available():
    """When `services.playbook_executor` IS the real module, `_update_code_source_worst_case_s()`
    must read THROUGH to its live constants, not always return the hardcoded
    fallback by coincidence. Proven by changing one constant on the real,
    loaded module and confirming the returned value moves with it -- at the
    unmodified defaults the real and fallback values are both 180.0, which
    alone would not distinguish "read through" from "always fell back".
    """
    spec = importlib.util.spec_from_file_location(
        "playbook_executor_for_worst_case_test", _SLM_ROOT / "services" / "playbook_executor.py"
    )
    real_playbook_executor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_playbook_executor)
    assert real_playbook_executor.update_code_source_worst_case_s() == 180.0  # sanity: matches the fallback here

    original_git_timeout = real_playbook_executor.GIT_COMMAND_TIMEOUT_S
    real_playbook_executor.GIT_COMMAND_TIMEOUT_S = 999
    original_module = sys.modules.get("services.playbook_executor")
    sys.modules["services.playbook_executor"] = real_playbook_executor
    try:
        worst_case = reconciler._update_code_source_worst_case_s()
    finally:
        real_playbook_executor.GIT_COMMAND_TIMEOUT_S = original_git_timeout
        if original_module is not None:
            sys.modules["services.playbook_executor"] = original_module

    assert worst_case != 180.0, "expected the raised GIT_COMMAND_TIMEOUT_S to change the computed worst case"
    # 999 replaces 3 of the 4 GIT_COMMAND_TIMEOUT_S-bounded terms (checkout,
    # fetch, reset -- rev-parse alone is bounded by the separate
    # GIT_REV_PARSE_TIMEOUT_S, left untouched), each still carrying its own
    # 4x-kill-grace worst case.
    kill_worst_case = 4 * real_playbook_executor.PLAYBOOK_KILL_GRACE_S
    expected_worst_case = 3 * (999 + kill_worst_case) + (
        real_playbook_executor.GIT_REV_PARSE_TIMEOUT_S + kill_worst_case
    )
    assert worst_case == expected_worst_case, f"expected {expected_worst_case}, got {worst_case}"


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
    assert (
        reconciler.SERVICE_RESTART_PLAYBOOK_TIMEOUT_S > reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
    ), "the service-restart budget must be the LARGER of the two for this test to mean anything"
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


def test_escalation_reachable_at_the_shipped_default_once_update_code_source_is_folded_in():
    """The actual fix for the reported "56 restarts / 0 escalations" shape, at
    the SHIPPED default (review round 3 -- corrects round 2's version of this
    test, which modelled `work_duration` as `REMEDIATION_PLAYBOOK_TIMEOUT_S +
    REMEDIATION_HEARTBEAT_WAIT_S` alone and concluded the pre-#14524 margin
    already covered the shipped default (floor 391s > gap 360s). That
    omitted `_update_code_source`'s own now-bounded worst case, which
    `execute_playbook` runs as part of the SAME attempt: with it included,
    `work_duration` is 450s (180 + 90 + 180), the real gap
    (`_gap_after_one_attempt(450)`) is 510s, and 510 > 391 -- the PRE-#14524
    margin does NOT cover the shipped default either, once the full attempt
    is modelled honestly. The floor extension is load-bearing here, not
    merely defensive -- see the sibling test below for a scenario where an
    operator-raised timeout widens the gap further still.
    """
    service = reconciler.ReconcilerService()
    clock = _Clock(datetime.now(timezone.utc))

    async def _bounded_but_successful_restart(*_args, **_kwargs):
        # Models the WHOLE `_restart_service_via_ansible` call this stubs --
        # execute_playbook runs _update_code_source before _run_subprocess,
        # as part of the same attempt.
        clock.advance(reconciler._update_code_source_worst_case_s() + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S)
        return True  # the run itself succeeds -- heartbeat is what never verifies

    async def _never_verifies(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_HEARTBEAT_WAIT_S)
        return False

    service._restart_service_via_ansible = _bounded_but_successful_restart
    service._heartbeat_returned = _never_verifies

    # Global monkeypatches (module-level `datetime`, `REMEDIATION_TRACKER_
    # EXPIRY_S`) are set and restored ENTIRELY inside try/finally (review,
    # round 3): an earlier version set them before `try:`, so an exception
    # raised between the assignment and the `try` line (however unlikely
    # today) would skip `finally` and leak a fake `datetime` into every
    # later test in the session.
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    try:
        reconciler.datetime = clock
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1  # force the floor, not the 1800s default, to be binding
        db = _FakeSession()
        node = _degraded_node()
        work_duration = (
            reconciler._update_code_source_worst_case_s()
            + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
            + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        )
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


def test_floor_extension_matters_more_once_an_operator_raises_the_playbook_timeout():
    """A second scenario where the #14524 floor extension is load-bearing,
    further past the shipped default than the sibling test above.

    `REMEDIATION_PLAYBOOK_TIMEOUT_S` is raised (in-test only) to 280 --
    `work_duration = update_code_source_worst_case + 280 + 90 = 550s`, the
    real gap (`_gap_after_one_attempt(550)`) is 610s, which exceeds the OLD
    margin's floor (391s, `REMEDIATION_HEARTBEAT_WAIT_S` alone) by an even
    wider margin than the sibling test's shipped-default scenario -- forgiven
    every cycle, escalation unreachable. The NEW margin folds in the raised
    timeout too (floor 851s) and does not forgive.
    """
    service = reconciler.ReconcilerService()
    clock = _Clock(datetime.now(timezone.utc))

    async def _slow_but_successful_restart(*_args, **_kwargs):
        clock.advance(reconciler._update_code_source_worst_case_s() + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S)
        return True

    async def _never_verifies(*_args, **_kwargs):
        clock.advance(reconciler.REMEDIATION_HEARTBEAT_WAIT_S)
        return False

    service._restart_service_via_ansible = _slow_but_successful_restart
    service._heartbeat_returned = _never_verifies

    # See the sibling test above for why these are set INSIDE try (review, round 3).
    original_playbook_timeout = reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    try:
        reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S = 280
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = 1
        reconciler.datetime = clock
        db = _FakeSession()
        node = _degraded_node()
        work_duration = (
            reconciler._update_code_source_worst_case_s()
            + reconciler.REMEDIATION_PLAYBOOK_TIMEOUT_S
            + reconciler.REMEDIATION_HEARTBEAT_WAIT_S
        )
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


def test_launch_failed_service_remediation_sweep_does_not_block_the_caller():
    """The finding-1-on-the-sibling-path fix (#14524, review round 3).

    `_run_loop` used to `await self._remediate_failed_services()` inline --
    fully serial with `_attempt_remediation`. A single failed
    `ServiceCategory.AUTOBOT` unit legitimately (or via timeout) consuming a
    meaningful fraction of `SERVICE_RESTART_PLAYBOOK_TIMEOUT_S` (2100s)
    inflated the NODE tracker's own inter-attempt gap past
    `_effective_tracker_expiry_s()`'s 1800s default with NO env override --
    `_forgive_if_expired` then reset the node tracker every pass and node
    escalation became permanently unreachable, re-entering the exact "56
    restarts / 0 escalations" shape #14524 exists to fix, through the
    sibling path this PR's own round-2 fix created.

    `_launch_failed_service_remediation_sweep` must return control to the
    caller WITHOUT waiting for `_remediate_failed_services()` to finish --
    proven with an `asyncio.Event` the stub only sets partway through a
    (simulated) long sweep; the launcher returning before that event is set
    is the discriminator.
    """
    service = reconciler.ReconcilerService()
    started = asyncio.Event()
    may_finish = asyncio.Event()
    finished = asyncio.Event()

    async def _slow_sweep():
        started.set()
        await may_finish.wait()
        finished.set()

    service._remediate_failed_services = _slow_sweep

    async def _go():
        service._launch_failed_service_remediation_sweep()
        # The launcher itself must not have awaited the sweep to completion --
        # give the event loop one tick to let the background task actually start.
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not finished.is_set(), "the sweep must not have completed synchronously inside the launcher"
        may_finish.set()
        await asyncio.wait_for(service._service_sweep_task, timeout=1)
        assert finished.is_set()

    asyncio.run(_go())


def test_launch_failed_service_remediation_sweep_skips_overlap():
    """Two sweeps racing the same `self._service_remediation_tracker` entries
    would corrupt cooldown/count bookkeeping -- a second launch while the
    first is still running must be a no-op, not a second concurrent task.
    """
    service = reconciler.ReconcilerService()
    still_running = asyncio.Event()

    async def _slow_sweep():
        await still_running.wait()

    service._remediate_failed_services = _slow_sweep

    async def _go():
        service._launch_failed_service_remediation_sweep()
        first_task = service._service_sweep_task
        await asyncio.sleep(0)  # let it actually start
        service._launch_failed_service_remediation_sweep()
        second_task = service._service_sweep_task
        assert first_task is second_task, "an overlapping launch must not replace the still-running task"
        still_running.set()
        await asyncio.wait_for(first_task, timeout=1)

    asyncio.run(_go())


def test_launch_failed_service_remediation_sweep_relaunches_once_the_previous_one_finished():
    """The overlap guard must not become a permanent latch -- once a sweep
    finishes, the next reconcile tick's launch must start a NEW task.
    """
    service = reconciler.ReconcilerService()
    call_count = {"n": 0}

    async def _fast_sweep():
        call_count["n"] += 1

    service._remediate_failed_services = _fast_sweep

    async def _go():
        service._launch_failed_service_remediation_sweep()
        await asyncio.wait_for(service._service_sweep_task, timeout=1)
        first_task = service._service_sweep_task
        service._launch_failed_service_remediation_sweep()
        second_task = service._service_sweep_task
        assert second_task is not first_task, "a finished sweep must not block the next tick's launch"
        await asyncio.wait_for(second_task, timeout=1)

    asyncio.run(_go())
    assert call_count["n"] == 2


def test_log_service_sweep_outcome_surfaces_an_exception_from_the_background_task():
    """A fire-and-forget task's exception is otherwise swallowed silently --
    `_run_loop`'s own broad `except Exception` no longer sees it once the
    sweep is launched instead of awaited inline, so the done-callback must
    surface it another way (logging here; asserted via caplog-free direct
    call to keep this test independent of logging configuration).
    """

    async def _broken_sweep():
        raise RuntimeError("boom")

    async def _go():
        task = asyncio.create_task(_broken_sweep())
        try:
            await task
        except RuntimeError:
            pass
        # Must not itself raise -- this is what a done-callback is required not to do.
        reconciler.ReconcilerService._log_service_sweep_outcome(task)

    asyncio.run(_go())  # must not raise
