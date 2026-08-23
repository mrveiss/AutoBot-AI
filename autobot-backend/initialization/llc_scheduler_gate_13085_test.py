# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC poll-loop schedulers must not run under pytest (#13085).

`_init_liveness_monitor`, `_init_budget_watchdog` and
`_start_community_clustering_loop` start infinite `while self._running` loops.
The shutdown path drains them via `aclose()` (#13182/#13203/#13210), but a drain
only helps if shutdown actually runs — a test that boots the real lifespan
through a TestClient/LifespanManager fixture and abandons the generator never
reaches teardown, so a loop keeps the event loop alive for a full re-armed
interval. #13085 measured that as an xdist worker frozen ~10 minutes at 99% with
zero CPU progress, its scheduled wake time advancing by exactly 300.1 s between
two py-spy dumps — BudgetWatchdog's 300 s interval.

The gate is default-ON and only switches off under pytest. That asymmetry is the
point and is asserted below: default-OFF (the AUTOBOT_ENABLE_MESH_SCHEDULER shape
from #12816) would silently stop enforcing per-agent budgets and recovering stuck
heartbeat runs in production, which is the same class of defect as GH#12318 —
scheduled work that quietly never runs.

Every test asserts WHICH branch was taken (start() called or not) rather than
only that the call returned, so a gate that lets the code through while looking
disabled cannot pass.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app():
    return SimpleNamespace(state=SimpleNamespace())


# ---------------------------------------------------------------------------
# The predicate itself
# ---------------------------------------------------------------------------


class TestGatePredicate:
    """`_llc_schedulers_enabled()` resolves the two env vars in the right order."""

    def test_disabled_under_pytest_by_default(self, monkeypatch):
        from initialization.lifespan import _llc_schedulers_enabled

        monkeypatch.delenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "some_test.py::test_x (call)")
        assert _llc_schedulers_enabled() is False

    def test_enabled_by_default_outside_pytest(self, monkeypatch):
        """Production default. A default-off gate would re-create GH#12318."""
        from initialization.lifespan import _llc_schedulers_enabled

        monkeypatch.delenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert _llc_schedulers_enabled() is True

    def test_explicit_on_overrides_the_pytest_marker(self, monkeypatch):
        """A test that wants the real loops can still ask for them."""
        from initialization.lifespan import _llc_schedulers_enabled

        monkeypatch.setenv("PYTEST_CURRENT_TEST", "some_test.py::test_x (call)")
        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "1")
        assert _llc_schedulers_enabled() is True

    def test_explicit_off_overrides_everything(self, monkeypatch):
        from initialization.lifespan import _llc_schedulers_enabled

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "0")
        assert _llc_schedulers_enabled() is False

    def test_read_at_call_time_not_import_time(self, monkeypatch):
        """pytest sets PYTEST_CURRENT_TEST per test, so a value captured at
        import would be stale for every lifespan a later test boots."""
        from initialization.lifespan import _llc_schedulers_enabled

        monkeypatch.delenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert _llc_schedulers_enabled() is True
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "some_test.py::test_y (call)")
        assert _llc_schedulers_enabled() is False


# ---------------------------------------------------------------------------
# The three call sites — assert the branch, not just the return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBudgetWatchdogGate:
    async def test_not_started_when_gated_off(self, app, monkeypatch):
        from initialization.lifespan import _init_budget_watchdog

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "0")
        instance = MagicMock()
        with patch("llc.scheduler.budget_watchdog.BudgetWatchdog", return_value=instance) as ctor:
            await _init_budget_watchdog(app)
        ctor.assert_not_called()
        instance.start.assert_not_called()
        assert app.state.llc_budget_watchdog is None

    async def test_started_when_gated_on(self, app, monkeypatch):
        from initialization.lifespan import _init_budget_watchdog

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "1")
        instance = MagicMock()
        with patch("llc.scheduler.budget_watchdog.BudgetWatchdog", return_value=instance):
            await _init_budget_watchdog(app)
        instance.start.assert_called_once()
        assert app.state.llc_budget_watchdog is instance


@pytest.mark.asyncio
class TestLivenessMonitorGate:
    async def test_not_started_when_gated_off(self, app, monkeypatch):
        from initialization.lifespan import _init_liveness_monitor

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "0")
        instance = MagicMock()
        with patch("llc.scheduler.liveness_monitor.LivenessMonitor", return_value=instance) as ctor:
            await _init_liveness_monitor(app)
        ctor.assert_not_called()
        instance.start.assert_not_called()
        assert app.state.llc_liveness_monitor is None

    async def test_started_when_gated_on(self, app, monkeypatch):
        from initialization.lifespan import _init_liveness_monitor

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "1")
        instance = MagicMock()
        with patch("llc.scheduler.liveness_monitor.LivenessMonitor", return_value=instance):
            await _init_liveness_monitor(app)
        instance.start.assert_called_once()
        assert app.state.llc_liveness_monitor is instance


@pytest.mark.asyncio
class TestCommunityClustererGate:
    async def test_not_started_when_gated_off(self, app, monkeypatch):
        """Gated off before the mesh_db lookup, so it cannot start at all."""
        from initialization.lifespan import _start_community_clustering_loop

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "0")
        app.state.mesh_db = MagicMock()
        instance = MagicMock()
        with patch(
            "llc.scheduler.community_cluster_scheduler.CommunityClusteringScheduler",
            return_value=instance,
        ) as ctor:
            await _start_community_clustering_loop(app)
        ctor.assert_not_called()
        instance.start.assert_not_called()
        assert app.state.community_cluster_scheduler is None

    async def test_started_when_gated_on(self, app, monkeypatch):
        from initialization.lifespan import _start_community_clustering_loop

        monkeypatch.setenv("AUTOBOT_ENABLE_LLC_SCHEDULERS", "1")
        app.state.mesh_db = MagicMock()
        instance = MagicMock()
        with patch(
            "llc.scheduler.community_cluster_scheduler.CommunityClusteringScheduler",
            return_value=instance,
        ):
            await _start_community_clustering_loop(app)
        instance.start.assert_called_once()
        assert app.state.community_cluster_scheduler is instance


# ---------------------------------------------------------------------------
# The intervals that make an abandoned loop expensive
# ---------------------------------------------------------------------------


class TestIntervalsAreConfigurable:
    """The 300 s / 6 h numbers are the whole cost of an abandoned loop, so they
    must be env-var-backed constants rather than literals.

    Asserted on the AST rather than by reloading the module. ``importlib.reload``
    would hand every already-imported test a stale ``CommunityClusteringScheduler``
    class whose globals no longer match the module that later ``patch()`` calls
    resolve against — ``community_cluster_scheduler_test`` patches
    ``_sleep`` by dotted path, so a stale class would sleep the real initial
    delay. The AST carries the same fact with no session-wide side effect.
    """

    EXPECTED = {
        "_CLUSTER_INTERVAL_SECONDS": ("LLC_COMMUNITY_CLUSTER_INTERVAL_SECONDS", 6 * 3600),
        "_INITIAL_DELAY_SECONDS": ("LLC_COMMUNITY_CLUSTER_INITIAL_DELAY_SECONDS", 300),
    }

    def _assignments(self):
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent.parent / "llc" / "scheduler" / "community_cluster_scheduler.py"
        ).read_text(encoding="utf-8")
        found = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                found[node.targets[0].id] = node.value
        return found

    @staticmethod
    def _int_value(node):
        """Numeric value of an int literal or a product of them (``6 * 3600``).

        ``ast.literal_eval`` rejects a ``BinOp`` of two ints, so asserting the
        real number rather than its spelling needs this much evaluation.
        """
        import ast

        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            return TestIntervalsAreConfigurable._int_value(node.left) * TestIntervalsAreConfigurable._int_value(
                node.right
            )
        raise AssertionError(f"default is not a constant expression: {ast.dump(node)}")

    def test_intervals_are_env_backed_with_unchanged_defaults(self):
        import ast

        found = self._assignments()
        for const, (env_var, default) in self.EXPECTED.items():
            assert const in found, f"{const} is no longer a module-level constant"
            value = found[const]
            assert isinstance(value, ast.Call) and getattr(value.func, "id", None) == "env_float", (
                f"{const} must be read from the environment via env_float(), not hard-coded"
            )
            assert ast.literal_eval(value.args[0]) == env_var, f"{const} must read {env_var}"
            assert self._int_value(value.args[1]) == default, f"{const} default changed unexpectedly"
